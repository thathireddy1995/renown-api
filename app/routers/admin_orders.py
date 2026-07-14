"""Admin orders — /admin/orders."""

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.admin_order_status import STATUS_LABEL, admin_status_label
from app.core.product_resolve import public_product_id
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminOrderDetailOut,
    AdminOrderItemOut,
    AdminOrderListResponse,
    AdminOrderOut,
    AdminOrderStatusUpdate,
)
from app.schemas import Customer, Order, OrderItem

router = APIRouter(prefix="/admin/orders", tags=["admin-orders"], dependencies=[Depends(require_role("admin"))])

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "placed": {"verified", "packed", "cancelled"},
    "verified": {"packed", "cancelled"},
    "packed": {"shipped", "cancelled"},
    "shipped": {"out", "delivered"},
    "out": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}

# Accept either DB keys or UI labels on PATCH.
STATUS_ALIASES = {
    "processing": "placed",
    "order placed": "placed",
    "prescription verified": "verified",
    "out for delivery": "out",
}


def _label(raw: str) -> str:
    return admin_status_label(raw)


def _normalize_status(value: str) -> str:
    key = (value or "").strip().lower()
    if key in ALLOWED_TRANSITIONS:
        return key
    if key in STATUS_ALIASES:
        return STATUS_ALIASES[key]
    for db_key, label in STATUS_LABEL.items():
        if label.lower() == key:
            return db_key
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Unknown status: {value}",
    )


def _parse_day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _parse_day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def _order_list_row(
    order: Order, customer_name: str | None, items: int
) -> AdminOrderOut:
    return AdminOrderOut(
        id=order.order_number,
        customer=customer_name or f"Customer #{order.customer_id}",
        date=order.created_at.strftime("%Y-%m-%d") if order.created_at else "",
        items=int(items or 0),
        status=_label(order.status),
        total=float(order.total or 0),
    )


def _order_to_list_row(order: Order) -> AdminOrderOut:
    customer = order.customer
    name = customer.name if customer else None
    return _order_list_row(order, name, len(order.items or []))


def _resolve_order(db: Session, order_ref: str) -> Order | None:
    """Resolve by numeric PK or order_number."""
    stmt = (
        select(Order)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.customer),
            selectinload(Order.address),
        )
    )
    if order_ref.isdigit():
        order = db.scalar(stmt.where(Order.id == int(order_ref)))
        if order:
            return order
    return db.scalar(stmt.where(Order.order_number == order_ref))


@router.get("", response_model=AdminOrderListResponse)
def list_orders(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> AdminOrderListResponse:
    limit, offset = page

    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.customer))
        .join(Customer, Customer.id == Order.customer_id)
    )
    count_stmt = (
        select(func.count())
        .select_from(Order)
        .join(Customer, Customer.id == Order.customer_id)
    )

    if status_filter:
        raw = status_filter.strip().lower()
        if raw in ("processing",):
            statuses = ["placed", "verified", "packed"]
        elif raw in STATUS_LABEL:
            statuses = [raw]
        else:
            # UI label → DB keys
            statuses = [k for k, v in STATUS_LABEL.items() if v.lower() == raw]
            if not statuses:
                try:
                    statuses = [_normalize_status(status_filter)]
                except HTTPException:
                    statuses = [raw]
        stmt = stmt.where(Order.status.in_(statuses))
        count_stmt = count_stmt.where(Order.status.in_(statuses))

    if date_from is not None:
        start = _parse_day_start(date_from)
        stmt = stmt.where(Order.created_at >= start)
        count_stmt = count_stmt.where(Order.created_at >= start)

    if date_to is not None:
        end = _parse_day_end(date_to)
        stmt = stmt.where(Order.created_at <= end)
        count_stmt = count_stmt.where(Order.created_at <= end)

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(Order.order_number.ilike(like), Customer.name.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    orders = db.scalars(
        stmt.order_by(Order.created_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).unique().all()

    return AdminOrderListResponse(
        items=[_order_to_list_row(order) for order in orders],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_ref}", response_model=AdminOrderDetailOut)
def get_order(order_ref: str, db: Session = Depends(get_db)) -> AdminOrderDetailOut:
    order = _resolve_order(db, order_ref)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    customer = order.customer
    line_items = [
        AdminOrderItemOut(
            productId=public_product_id(i.product) if i.product else str(i.product_id),
            name=i.name_snapshot or (i.product.name if i.product else ""),
            qty=i.qty,
            price=float(i.price_snapshot or 0),
        )
        for i in (order.items or [])
    ]
    base = _order_list_row(
        order,
        customer.name if customer else None,
        len(order.items or []),
    )
    return AdminOrderDetailOut(
        **base.model_dump(),
        db_id=order.id,
        customer_id=order.customer_id,
        customer_email=customer.email if customer else None,
        customer_phone=customer.phone if customer else None,
        subtotal=float(order.subtotal or 0),
        discount=float(order.discount or 0),
        shipping=float(order.shipping_fee or 0),
        tax=float(order.tax or 0),
        coupon_code=order.coupon_code,
        line_items=line_items,
    )


@router.patch("/{order_ref}/status", response_model=AdminOrderDetailOut)
def update_order_status(
    order_ref: str,
    body: AdminOrderStatusUpdate,
    db: Session = Depends(get_db),
) -> AdminOrderDetailOut:
    order = _resolve_order(db, order_ref)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    new_status = _normalize_status(body.status)
    current = (order.status or "placed").lower()
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if new_status != current and new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot transition from '{current}' to '{new_status}'",
        )

    order.status = new_status
    db.commit()
    refreshed = _resolve_order(db, order_ref)
    if not refreshed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    customer = refreshed.customer
    line_items = [
        AdminOrderItemOut(
            productId=public_product_id(i.product) if i.product else str(i.product_id),
            name=i.name_snapshot or (i.product.name if i.product else ""),
            qty=i.qty,
            price=float(i.price_snapshot or 0),
        )
        for i in (refreshed.items or [])
    ]
    base = _order_list_row(
        refreshed,
        customer.name if customer else None,
        len(refreshed.items or []),
    )
    return AdminOrderDetailOut(
        **base.model_dump(),
        db_id=refreshed.id,
        customer_id=refreshed.customer_id,
        customer_email=customer.email if customer else None,
        customer_phone=customer.phone if customer else None,
        subtotal=float(refreshed.subtotal or 0),
        discount=float(refreshed.discount or 0),
        shipping=float(refreshed.shipping_fee or 0),
        tax=float(refreshed.tax or 0),
        coupon_code=refreshed.coupon_code,
        line_items=line_items,
    )
