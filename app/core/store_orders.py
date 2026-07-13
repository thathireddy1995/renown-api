"""Shared store-order queries and serializers (Phase 10)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.schemas import Store, StoreOrder, StoreOrderItem

CHANNEL_ADMIN_TYPE = {
    "in_store": "POS",
    "click_collect": "Pickup",
    "home_delivery": "Pickup",
}

CHANNEL_STAFF_LABEL = {
    "in_store": "In-store",
    "click_collect": "Click & Collect",
    "home_delivery": "Home Delivery",
}

PAYMENT_LABEL = {
    "card": "Card",
    "upi": "UPI",
    "cash": "Cash",
    "online": "Online",
}

STAFF_STATUS = {
    "completed": "Paid",
    "paid": "Paid",
    "processing": "Processing",
    "pending": "Pending",
    "preparing": "Processing",
    "ready": "Processing",
    "collected": "Delivered",
    "delivered": "Delivered",
    "missed": "Cancelled",
    "void": "Cancelled",
    "cancelled": "Cancelled",
    "refund pending": "Cancelled",
}


def store_order_eager():
    return (
        selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant),
        selectinload(StoreOrder.store),
    )


def list_store_orders_query(
    *,
    store_id: int | None = None,
    status: str | None = None,
    channel: str | None = None,
    search: str | None = None,
    store_name: str | None = None,
):
    stmt = select(StoreOrder).options(*store_order_eager()).join(
        Store, Store.id == StoreOrder.store_id
    )
    count_stmt = (
        select(func.count())
        .select_from(StoreOrder)
        .join(Store, Store.id == StoreOrder.store_id)
    )

    if store_id is not None:
        stmt = stmt.where(StoreOrder.store_id == store_id)
        count_stmt = count_stmt.where(StoreOrder.store_id == store_id)

    if store_name and store_name not in ("all", "All", ""):
        stmt = stmt.where(Store.name == store_name)
        count_stmt = count_stmt.where(Store.name == store_name)

    if status and status.lower() not in ("all", ""):
        stmt = stmt.where(StoreOrder.status == status)
        count_stmt = count_stmt.where(StoreOrder.status == status)

    if channel:
        key = channel.strip().lower().replace(" ", "_").replace("&", "")
        mapped = {
            "in-store": "in_store",
            "instore": "in_store",
            "in_store": "in_store",
            "click_collect": "click_collect",
            "clickcollect": "click_collect",
            "home_delivery": "home_delivery",
            "homedelivery": "home_delivery",
            "pos": "in_store",
            "pickup": "click_collect",
        }.get(key, channel)
        stmt = stmt.where(StoreOrder.channel == mapped)
        count_stmt = count_stmt.where(StoreOrder.channel == mapped)

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            StoreOrder.order_number.ilike(like),
            StoreOrder.customer_name.ilike(like),
            StoreOrder.associate_name.ilike(like),
            StoreOrder.payment_method.ilike(like),
            StoreOrder.status.ilike(like),
            StoreOrder.channel.ilike(like),
            Store.name.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    return stmt, count_stmt


def format_inr_en(n: float) -> str:
    return f"₹{int(round(n)):,}"


def admin_order_row(o: StoreOrder) -> dict:
    return {
        "id": o.order_number,
        "store": o.store.name if o.store else "",
        "customer": o.customer_name or "Walk-in",
        "items": len(o.items or []),
        "total": float(o.total or 0),
        "payment": PAYMENT_LABEL.get(
            (o.payment_method or "").lower(), (o.payment_method or "").title()
        ),
        "associate": o.associate_name or "—",
        "time": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "",
        "status": o.status,
        "type": CHANNEL_ADMIN_TYPE.get(o.channel, "POS"),
    }


def staff_order_row(o: StoreOrder) -> dict:
    key = (o.status or "").lower()
    return {
        "id": o.order_number,
        "customer": o.customer_name or "Walk-in",
        "items": len(o.items or []),
        "channel": CHANNEL_STAFF_LABEL.get(o.channel, o.channel),
        "total": format_inr_en(float(o.total or 0)),
        "status": STAFF_STATUS.get(key, o.status),
        "date": _relative(o.created_at),
    }


def _relative(when: datetime | None) -> str:
    if when is None:
        return "—"
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    days = (now.date() - when.date()).days
    if days == 0:
        return f"Today {when.strftime('%H:%M')}"
    if days == 1:
        return "Yesterday"
    return f"{days}d ago"
