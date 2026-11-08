"""Order cancellation for web orders and their store pickup copies.

Click & collect orders exist twice: the web ``Order`` (what admin and the
customer see) and a ``StoreOrder`` with the same order_number (what the store
works from). Cancelling one closes the other and frees the held warehouse
stock once. Callers commit, then send the WhatsApp update for the side they
changed — the twin is updated silently so the customer gets one message.

Home-delivery web orders may also hold a Shiprocket booking and, once the
warehouse has assigned a partner, a dispatch that already took stock off the
shelf. Cancelling voids the booking and puts that stock back.
"""

from __future__ import annotations

import logging

import requests
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.order_club import club_children, club_lead, parcel_booked
from app.core.order_reservation import release_order_lines
from app.core.shiprocket import ShiprocketError, cancel_orders, configured, get_order
from app.schemas import DispatchOrder, Order, StoreOrder, WarehouseInventory

logger = logging.getLogger(__name__)

# Before packing nothing has left the shelf, so the customer may cancel.
CUSTOMER_CANCELLABLE = ("placed", "verified")
# Admin may cancel until the courier has picked the parcel up.
ADMIN_CANCELLABLE = ("placed", "verified", "packed", "partner_assigned")
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


def _shiprocket_already_cancelled(shiprocket_order_id: str) -> bool:
    try:
        data = get_order(shiprocket_order_id)
    except (ShiprocketError, requests.RequestException):
        return False
    return "cancel" in str(data.get("status") or "").lower()


def cancel_courier_booking(order: Order) -> None:
    """Void the order's Shiprocket booking before it is cancelled locally.

    With an AWB the courier may still turn up, so a refusal stops the cancel.
    Without one the booking is only a draft, so failures are just logged.
    """
    sr_id = (order.shiprocket_order_id or "").strip()
    if not sr_id or not configured():
        return
    try:
        cancel_orders([sr_id])
    except (ShiprocketError, requests.RequestException) as err:
        if _shiprocket_already_cancelled(sr_id):
            return
        if order.awb_code:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Shiprocket did not cancel AWB {order.awb_code}: {err}. "
                    "Cancel it in Shiprocket, then retry."
                ),
            ) from err
        logger.warning("Shiprocket cancel failed for %s: %s", order.order_number, err)


def _undo_open_dispatches(db: Session, order: Order) -> None:
    """Return stock a warehouse dispatch already deducted, and close the dispatch."""
    dispatches = db.scalars(
        select(DispatchOrder)
        .options(selectinload(DispatchOrder.items))
        .where(
            DispatchOrder.order_id == order.id,
            func.lower(DispatchOrder.status) != "cancelled",
        )
        .with_for_update(of=DispatchOrder)
    ).all()
    for dispatch in dispatches:
        for item in dispatch.items or []:
            row = db.scalar(
                select(WarehouseInventory)
                .where(
                    WarehouseInventory.warehouse_id == dispatch.warehouse_id,
                    WarehouseInventory.variant_id == item.variant_id,
                )
                .with_for_update()
            )
            if row is not None:
                row.on_hand = int(row.on_hand or 0) + int(item.qty or 0)
        dispatch.status = "Cancelled"


def cancel_web_order(db: Session, order: Order) -> str | None:
    """Cancel a web order: void its courier booking, undo any dispatch, free
    its stock and close the store copy.

    Returns the previous status, or None when the order was already closed.
    """
    return cancel_order_and_parcel(db, order)[0]


def cancel_order_and_parcel(
    db: Session, order: Order
) -> tuple[str | None, list[tuple[Order, str]]]:
    """Like ``cancel_web_order``, also handling clubbed parcels.

    Before booking, a clubbed order just leaves the parcel and the rest ship
    without it. Once booked, the parcel is one courier shipment: cancelling
    the lead cancels every order in it, and a clubbed order can't be cancelled
    on its own. Returns (previous status, [(clubbed order, previous status)])
    so the caller can notify each customer order that was cancelled.
    """
    previous = (order.status or "placed").lower()
    if previous in _WEB_CLOSED:
        return None, []

    lead = club_lead(db, order)
    if lead is not None:
        if parcel_booked(db, lead):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{order.order_number} ships in {lead.order_number}'s parcel. "
                    f"Cancel {lead.order_number} to cancel the whole parcel."
                ),
            )
        order.clubbed_into_id = None

    children = club_children(db, order, selectinload(Order.items))
    booked = bool(children) and parcel_booked(db, order)
    if children and not booked:
        for child in children:
            child.clubbed_into_id = None

    cancel_courier_booking(order)
    order.status = "cancelled"
    _undo_open_dispatches(db, order)
    release_order_stock(db, order)
    close_store_copy(db, order.order_number)

    cancelled: list[tuple[Order, str]] = []
    if booked:
        for child in children:
            child_previous = (child.status or "placed").lower()
            if child_previous in _WEB_CLOSED:
                continue
            child.status = "cancelled"
            release_order_stock(db, child)
            close_store_copy(db, child.order_number)
            cancelled.append((child, child_previous))
    return previous, cancelled


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
