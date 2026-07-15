"""Customer orders — /customer/orders (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.order_service import (
    create_order_record,
    load_cart_lines,
    resolve_shipping_address,
)
from app.core.product_resolve import public_product_id
from app.database import get_db
from app.deps import get_current_customer, pagination
from app.dto.order_dto import (
    OrderCreateRequest,
    OrderItemOut,
    OrderListResponse,
    OrderOut,
)
from app.schemas import Customer, Order, OrderItem

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
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        items=items,
    )


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
    """Cash-on-delivery / no-gateway checkout. Online payments go through
    /customer/payments (see customer_payments.py) — an Order row there is
    only written *after* Razorpay confirms the payment."""
    line_rows, subtotal = load_cart_lines(db, customer)
    address_id = resolve_shipping_address(db, customer, payload.address_id, payload.delivery or "ship")

    order = create_order_record(
        db,
        customer,
        address_id=address_id,
        delivery=payload.delivery or "ship",
        coupon_code=payload.coupon_code,
        line_rows=line_rows,
        subtotal=subtotal,
        payment_method="cod",
        payment_status="pending",
    )
    return _order_out(order)
