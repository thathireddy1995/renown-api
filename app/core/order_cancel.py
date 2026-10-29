"""Keep an online order and its store pickup copy in step when either is cancelled.

Click & collect orders exist twice: the web ``Order`` (what admin and the
customer see) and a ``StoreOrder`` with the same order_number (what the store
works from). Cancelling one closes the other and frees the held warehouse
stock once. Callers commit, then send the WhatsApp update for the side they
changed — the twin is updated silently so the customer gets one message.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.order_reservation import release_order_lines
from app.schemas import Order, StoreOrder

# Before packing nothing has left the shelf, so the customer may cancel.
CUSTOMER_CANCELLABLE = ("placed", "verified")
_STORE_CLOSED = ("collected", "delivered", "completed", "cancelled", "missed", "void")
_WEB_CLOSED = ("cancelled", "delivered")


def release_order_stock(db: Session, order: Order) -> None:
    release_order_lines(db, [(item.variant_id, item.qty) for item in (order.items or [])])


def close_store_copy(db: Session, order_number: str) -> StoreOrder | None:
    """The web order was cancelled: cancel its open store pickup copy, if any."""
    copy = db.scalar(
        select(StoreOrder).where(StoreOrder.order_number == order_number).with_for_update()
    )
    if copy is None or (copy.status or "").lower() in _STORE_CLOSED:
        return None
    copy.status = "Cancelled"
    return copy


def cancel_web_order(db: Session, order: Order) -> str | None:
    """Cancel a web order, free its stock and close the store copy.

    Returns the previous status, or None when the order was already closed.
    """
    previous = (order.status or "placed").lower()
    if previous in _WEB_CLOSED:
        return None
    order.status = "cancelled"
    release_order_stock(db, order)
    close_store_copy(db, order.order_number)
    return previous


def cancel_web_twin(db: Session, store_order: StoreOrder) -> Order | None:
    """The store cancelled or missed its pickup copy: cancel the web order too."""
    order = db.scalar(
        select(Order)
        .where(Order.order_number == store_order.order_number)
        .options(selectinload(Order.items))
        .with_for_update(of=Order)
    )
    if order is None or (order.status or "").lower() in _WEB_CLOSED:
        return None
    order.status = "cancelled"
    release_order_stock(db, order)
    return order
