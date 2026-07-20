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
from app.core.shiprocket import (
    ShiprocketError,
    configured as shiprocket_configured,
    normalize_tracking,
    track_by_awb,
)
from app.dto.order_dto import (
    OrderCreateRequest,
    OrderItemOut,
    OrderListResponse,
    OrderOut,
    OrderTrackingOut,
    TrackingActivityOut,
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
        awb_code=order.awb_code,
        courier_name=order.courier_name,
        tracking_url=order.tracking_url,
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


@router.get("/{order_number}/tracking", response_model=OrderTrackingOut)
def track_order(
    order_number: str,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderTrackingOut:
    """Order timeline + live Shiprocket events when an AWB is attached."""
    order = db.scalar(
        select(Order).where(
            Order.order_number == order_number,
            Order.customer_id == customer.id,
        )
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    base = OrderTrackingOut(
        order_id=order.order_number,
        status=_status_label(order.status),
        awb_code=order.awb_code,
        courier_name=order.courier_name,
        tracking_url=order.tracking_url,
        shiprocket=False,
    )

    if not order.awb_code:
        base.message = "Shipment not handed to courier yet."
        return base

    if not shiprocket_configured():
        base.message = "Tracking service is not configured."
        return base

    try:
        raw = track_by_awb(order.awb_code)
        info = normalize_tracking(raw)
    except ShiprocketError as err:
        base.message = str(err)
        return base

    # Keep Renown order status in sync with courier when it advances.
    mapped = info.get("mapped_status") or ""
    if mapped and mapped != (order.status or "").lower():
        order.status = mapped
        if info.get("courier") and not order.courier_name:
            order.courier_name = info["courier"][:120]
        if info.get("track_url"):
            order.tracking_url = info["track_url"]
        db.commit()

    return OrderTrackingOut(
        order_id=order.order_number,
        status=_status_label(order.status),
        awb_code=order.awb_code or info.get("awb") or None,
        courier_name=order.courier_name or info.get("courier") or None,
        tracking_url=order.tracking_url or info.get("track_url") or None,
        current_status=info.get("current_status") or None,
        edd=info.get("edd") or None,
        origin=info.get("origin") or None,
        destination=info.get("destination") or None,
        activities=[TrackingActivityOut(**a) for a in info.get("activities") or []],
        shiprocket=True,
        message=None,
    )


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
