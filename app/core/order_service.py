"""Shared order-creation logic used by customer_orders and customer_payments.

Kept in one place so the pricing rules and the "cart -> Order row" write path
can never drift between the COD flow and the Razorpay flow.
"""

import secrets
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.schemas import Address, CartItem, Customer, Order, OrderItem


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
    """Mirror cart.tsx / checkout.tsx rules."""
    code = (coupon_code or "").strip().upper() or None
    discount = Decimal("0")
    if code == "RENOWN15":
        discount = (subtotal * Decimal("0.15")).quantize(Decimal("0.01"))

    if delivery == "pickup":
        shipping = Decimal("0")
    else:
        shipping = Decimal("0") if subtotal > Decimal("75") or subtotal == 0 else Decimal("8")

    tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
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
) -> Order:
    """Write the Order + OrderItems and clear the cart in one transaction."""
    discount, shipping, tax, total, coupon = compute_pricing(subtotal, delivery or "ship", coupon_code)

    order = Order(
        order_number=next_order_number(db),
        customer_id=customer.id,
        address_id=address_id,
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

    db.add_all(
        [
            OrderItem(
                order_id=order.id,
                product_id=row.product_id,
                variant_id=row.variant_id,
                name_snapshot=row.product.name,
                price_snapshot=unit,
                qty=row.qty,
            )
            for row, unit in line_rows
        ]
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
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    assert reloaded is not None
    return reloaded
