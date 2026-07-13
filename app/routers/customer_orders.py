"""Customer orders — /customer/orders (JWT required)."""

import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.product_resolve import public_product_id
from app.database import get_db
from app.deps import get_current_customer, pagination
from app.dto.order_dto import (
    OrderCreateRequest,
    OrderItemOut,
    OrderListResponse,
    OrderOut,
)
from app.schemas import (
    Address,
    CartItem,
    Customer,
    Order,
    OrderItem,
)

router = APIRouter(prefix="/customer/orders", tags=["customer-orders"])

STATUS_LABEL = {
    "placed": "Order Placed",
    "verified": "Prescription Verified",
    "packed": "Packed",
    "shipped": "Shipped",
    "out": "Out for Delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def _status_label(raw: str) -> str:
    return STATUS_LABEL.get((raw or "").lower(), raw or "Order Placed")


def _order_out(order: Order) -> OrderOut:
    items = [
        OrderItemOut(
            productId=public_product_id(i.product) if i.product else str(i.product_id),
            name=i.name_snapshot or (i.product.name if i.product else ""),
            qty=i.qty,
            price=float(i.price_snapshot or 0),
        )
        for i in (order.items or [])
    ]
    return OrderOut(
        id=order.order_number,
        date=order.created_at.strftime("%Y-%m-%d") if order.created_at else "",
        status=_status_label(order.status),
        total=float(order.total or 0),
        subtotal=float(order.subtotal or 0),
        discount=float(order.discount or 0),
        shipping=float(order.shipping_fee or 0),
        tax=float(order.tax or 0),
        coupon_code=order.coupon_code,
        items=items,
    )


def _next_order_number(db: Session) -> str:
    for _ in range(8):
        num = f"RO-{secrets.randbelow(90_000) + 10_000}"
        exists = db.scalar(select(Order.id).where(Order.order_number == num))
        if not exists:
            return num
    return f"RO-{secrets.randbelow(900_000) + 100_000}"


def _pricing(
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


@router.get("/", response_model=OrderListResponse)
def list_orders(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
    page: tuple[int, int] = Depends(pagination),
) -> OrderListResponse:
    limit, offset = page
    total = (
        db.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.customer_id == customer.id)
        )
        or 0
    )
    rows = db.scalars(
        select(Order)
        .where(Order.customer_id == customer.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
        )
        .order_by(Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return OrderListResponse(
        items=[_order_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_number}", response_model=OrderOut)
def get_order(
    order_number: str,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderOut:
    order = db.scalar(
        select(Order)
        .where(
            Order.order_number == order_number,
            Order.customer_id == customer.id,
        )
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return _order_out(order)


@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreateRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderOut:
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

    address_id = payload.address_id
    if payload.delivery != "pickup":
        if address_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="address_id is required for shipping.",
            )
        address = db.scalar(
            select(Address).where(
                Address.id == address_id, Address.customer_id == customer.id
            )
        )
        if not address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid address.",
            )
    else:
        address_id = None

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

    discount, shipping, tax, total, coupon = _pricing(
        subtotal, payload.delivery or "ship", payload.coupon_code
    )

    order = Order(
        order_number=_next_order_number(db),
        customer_id=customer.id,
        address_id=address_id,
        status="placed",
        subtotal=subtotal,
        discount=discount,
        shipping_fee=shipping,
        tax=tax,
        total=total,
        coupon_code=coupon,
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

    db.execute(delete(CartItem).where(CartItem.customer_id == customer.id, CartItem.saved_for_later.is_(False)))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    order = db.scalar(
        select(Order)
        .where(Order.id == order.id)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    assert order is not None
    return _order_out(order)
