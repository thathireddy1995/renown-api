"""Shared order-creation logic used by customer_orders and customer_payments.

Kept in one place so the pricing rules and the "cart -> Order row" write path
can never drift between the COD flow and the Razorpay flow.
"""

import secrets
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.schemas import (
    Address,
    CartItem,
    Customer,
    Order,
    OrderItem,
    ProductVariant,
    Store,
    StoreOrder,
    StoreOrderItem,
)


def next_order_number(db: Session) -> str:
    for _ in range(8):
        num = f"RO-{secrets.randbelow(90_000) + 10_000}"
        exists = db.scalar(select(Order.id).where(Order.order_number == num))
        if not exists:
            return num
    return f"RO-{secrets.randbelow(900_000) + 100_000}"


def compute_pricing(
    subtotal: Decimal, delivery: str, coupon_code: str | None
) -> tuple[Decimal, Decimal, Decimal, Decimal, str | None]:
    """Cart / checkout pricing (INR). Coupons require a promotions API — no demo codes."""
    code = (coupon_code or "").strip().upper() or None
    discount = Decimal("0")

    if delivery == "pickup":
        shipping = Decimal("0")
    else:
        # Free standard shipping over ₹5,999 (matches storefront copy).
        shipping = Decimal("0") if subtotal >= Decimal("5999") or subtotal == 0 else Decimal("99")

    # Tax disabled for now — all products are zero-rated.
    tax = Decimal("0")
    total = subtotal + shipping + tax - discount
    if total < 0:
        total = Decimal("0")
    return discount, shipping, tax, total, code


def load_cart_lines(
    db: Session, customer: Customer
) -> tuple[list[tuple[CartItem, Decimal]], Decimal]:
    """Return (row, unit_price) pairs for the customer's active cart plus the subtotal."""
    cart_rows = db.scalars(
        select(CartItem)
        .where(
            CartItem.customer_id == customer.id,
            CartItem.saved_for_later.is_(False),
        )
        .options(selectinload(CartItem.product), selectinload(CartItem.variant))
    ).all()
    if not cart_rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart is empty.",
        )

    subtotal = Decimal("0")
    line_rows: list[tuple[CartItem, Decimal]] = []
    for row in cart_rows:
        if not row.product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cart contains an invalid product.",
            )
        unit = row.variant.price if row.variant and row.variant.price is not None else row.product.price
        unit = Decimal(str(unit))
        subtotal += unit * row.qty
        line_rows.append((row, unit))
    return line_rows, subtotal


def resolve_shipping_address(
    db: Session, customer: Customer, address_id: int | None, delivery: str
) -> int | None:
    """Validate the chosen address for a "ship" order; returns None for pickup."""
    if delivery == "pickup":
        return None
    if address_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="address_id is required for shipping.",
        )
    address = db.scalar(
        select(Address).where(Address.id == address_id, Address.customer_id == customer.id)
    )
    if not address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid address.",
        )
    return address_id


def resolve_pickup_store(
    db: Session, delivery: str, pickup_store_id: int | None
) -> int | None:
    """Validate the chosen store for pickup; returns None for ship orders."""
    if delivery != "pickup":
        return None
    if pickup_store_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pickup_store_id is required for store pickup.",
        )
    store = db.get(Store, pickup_store_id)
    if not store:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pickup store.",
        )
    return store.id


def _resolve_line_variant_id(db: Session, row: CartItem) -> int:
    if row.variant_id:
        return row.variant_id
    variant_id = db.scalar(
        select(ProductVariant.id)
        .where(
            ProductVariant.product_id == row.product_id,
            ProductVariant.color != "__deleted__",
            ProductVariant.size != "__deleted__",
        )
        .order_by(ProductVariant.id.asc())
        .limit(1)
    )
    if variant_id is None:
        variant_id = db.scalar(
            select(ProductVariant.id)
            .where(ProductVariant.product_id == row.product_id)
            .order_by(ProductVariant.id.asc())
            .limit(1)
        )
    if variant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product {row.product.name if row.product else row.product_id} has no variants for store pickup.",
        )
    return variant_id


def _create_pickup_store_order(
    db: Session,
    *,
    customer: Customer,
    store_id: int,
    order_number: str,
    line_rows: list[tuple[CartItem, Decimal]],
    subtotal: Decimal,
    tax: Decimal,
    total: Decimal,
    payment_method: str,
) -> None:
    """Mirror a click-and-collect ecommerce order into store_orders for staff."""
    pay = "online" if payment_method == "razorpay" else "cash"
    store_order = StoreOrder(
        order_number=order_number,
        store_id=store_id,
        customer_name=customer.name or customer.email or customer.phone or "Customer",
        channel="click_collect",
        payment_method=pay,
        associate_name=None,
        subtotal=subtotal,
        tax=tax,
        total=total,
        status="Preparing",
    )
    db.add(store_order)
    db.flush()

    db.add_all(
        [
            StoreOrderItem(
                store_order_id=store_order.id,
                variant_id=_resolve_line_variant_id(db, row),
                qty=row.qty,
                price_snapshot=unit,
            )
            for row, unit in line_rows
        ]
    )


def create_order_record(
    db: Session,
    customer: Customer,
    *,
    address_id: int | None,
    delivery: str,
    coupon_code: str | None,
    line_rows: list[tuple[CartItem, Decimal]],
    subtotal: Decimal,
    payment_method: str,
    payment_status: str,
    razorpay_order_id: str | None = None,
    razorpay_payment_id: str | None = None,
    pickup_store_id: int | None = None,
) -> Order:
    """Write the Order + OrderItems and clear the cart in one transaction.

    Store pickup also creates a matching StoreOrder (channel=click_collect)
    so the order appears on the staff store Orders screen.
    """
    discount, shipping, tax, total, coupon = compute_pricing(subtotal, delivery or "ship", coupon_code)
    store_id = resolve_pickup_store(db, delivery or "ship", pickup_store_id)
    mode = "pickup" if store_id is not None else (delivery or "ship")

    order = Order(
        order_number=next_order_number(db),
        customer_id=customer.id,
        address_id=address_id,
        delivery=mode,
        pickup_store_id=store_id,
        status="placed",
        subtotal=subtotal,
        discount=discount,
        shipping_fee=shipping,
        tax=tax,
        total=total,
        coupon_code=coupon,
        payment_method=payment_method,
        payment_status=payment_status,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
    )
    db.add(order)
    db.flush()

    order_items: list[OrderItem] = []
    for row, unit in line_rows:
        variant_id = row.variant_id
        if variant_id is None:
            try:
                variant_id = _resolve_line_variant_id(db, row)
            except HTTPException:
                variant_id = None
        order_items.append(
            OrderItem(
                order_id=order.id,
                product_id=row.product_id,
                variant_id=variant_id,
                name_snapshot=row.product.name,
                price_snapshot=unit,
                qty=row.qty,
            )
        )
    db.add_all(order_items)

    if store_id is not None:
        _create_pickup_store_order(
            db,
            customer=customer,
            store_id=store_id,
            order_number=order.order_number,
            line_rows=line_rows,
            subtotal=subtotal,
            tax=tax,
            total=total,
            payment_method=payment_method,
        )

    db.execute(
        delete(CartItem).where(
            CartItem.customer_id == customer.id, CartItem.saved_for_later.is_(False)
        )
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    reloaded = db.scalar(
        select(Order)
        .where(Order.id == order.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.address),
            selectinload(Order.pickup_store),
        )
    )
    assert reloaded is not None
    return reloaded
