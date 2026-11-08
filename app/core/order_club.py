"""Club several home-delivery orders from one customer into a single parcel.

The order the others are clubbed into (the "lead") carries the one Shiprocket
booking, the warehouse dispatch and the AWB. Clubbed orders keep their own
items, totals and invoices, but mirror the lead's courier fields and status.

Clubbing is only allowed before a delivery partner is assigned: after that
the parcel is booked and its contents can't change.
"""

from __future__ import annotations

import re

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas import DispatchOrder, Order

CLUBBABLE_STATUSES = ("placed", "verified", "packed")
_SHIP_MODES = ("ship", "home", "delivery")


def is_prepaid(order: Order) -> bool:
    return (order.payment_method or "").lower() == "razorpay" and (
        order.payment_status or ""
    ).lower() == "paid"


def destination_key(order: Order) -> tuple[str, str] | None:
    """Normalised (street, pincode) so the same address saved twice still matches."""
    address = order.address
    if address is None:
        return None
    street = re.sub(r"[^a-z0-9]", "", f"{address.line1 or ''}{address.line2 or ''}".lower())
    pin = re.sub(r"\D", "", address.postal_code or "")[:6]
    return (street, pin)


def club_group_key(order: Order) -> tuple | None:
    """Orders with the same key can share a parcel."""
    dest = destination_key(order)
    if dest is None:
        return None
    return (order.customer_id, dest, is_prepaid(order))


def club_children(db: Session, lead: Order, *options) -> list[Order]:
    return list(
        db.scalars(
            select(Order)
            .options(*options)
            .where(Order.clubbed_into_id == lead.id)
            .order_by(Order.id)
        ).all()
    )


def club_lead(db: Session, order: Order) -> Order | None:
    if not order.clubbed_into_id:
        return None
    return db.get(Order, order.clubbed_into_id)


def _has_open_dispatch(db: Session, order: Order) -> bool:
    return bool(
        db.scalar(
            select(DispatchOrder.id).where(
                DispatchOrder.order_id == order.id,
                func.lower(DispatchOrder.status) != "cancelled",
            )
        )
    )


def _ensure_clubbable(db: Session, order: Order) -> None:
    if (order.delivery or "ship").lower() not in _SHIP_MODES:
        raise HTTPException(status_code=422, detail=f"{order.order_number} is not a home delivery")
    if (order.status or "placed").lower() not in CLUBBABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"{order.order_number} already has a delivery partner and can't be clubbed",
        )
    if order.awb_code or _has_open_dispatch(db, order):
        raise HTTPException(
            status_code=409, detail=f"{order.order_number} is already booked with a courier"
        )


def club_orders(db: Session, lead: Order, other: Order) -> None:
    """Ship ``other`` (and anything already clubbed into it) in ``lead``'s parcel."""
    if lead.id == other.id:
        raise HTTPException(status_code=422, detail="Pick a different order to club with")
    if lead.clubbed_into_id:
        raise HTTPException(
            status_code=409, detail=f"{lead.order_number} is already clubbed into another order"
        )
    _ensure_clubbable(db, lead)
    _ensure_clubbable(db, other)
    if lead.customer_id != other.customer_id:
        raise HTTPException(status_code=422, detail="Only orders from the same customer can be clubbed")
    if destination_key(lead) != destination_key(other):
        raise HTTPException(
            status_code=422, detail="Orders ship to different addresses and can't share a parcel"
        )
    if is_prepaid(lead) != is_prepaid(other):
        raise HTTPException(
            status_code=422,
            detail="Can't club a prepaid order with a cash-on-delivery order",
        )

    for child in club_children(db, other):
        child.clubbed_into_id = lead.id
    other.clubbed_into_id = lead.id


def club_many(db: Session, orders: list[Order]) -> Order:
    """Put ``orders`` in one parcel and return its lead.

    An order that already leads a parcel stays the lead; otherwise the
    oldest order does. Caller commits.
    """
    unique = list({o.id: o for o in orders}.values())
    if len(unique) < 2:
        raise HTTPException(status_code=422, detail="Select at least two orders to club")
    leads = [o for o in unique if not o.clubbed_into_id and club_children(db, o)]
    lead = leads[0] if leads else min(unique, key=lambda o: o.id)
    if lead.clubbed_into_id:
        lead = club_lead(db, lead) or lead
    for other in unique:
        if other.id != lead.id and other.clubbed_into_id != lead.id:
            club_orders(db, lead, other)
    return lead


def parcel_booked(db: Session, lead: Order) -> bool:
    """True once a partner is assigned and the parcel's contents are fixed."""
    return (
        (lead.status or "placed").lower() not in CLUBBABLE_STATUSES
        or bool(lead.awb_code)
        or _has_open_dispatch(db, lead)
    )


def unclub_order(db: Session, order: Order) -> None:
    """Take ``order`` out of its parcel so it ships on its own again."""
    lead = club_lead(db, order)
    if lead is None:
        raise HTTPException(status_code=409, detail=f"{order.order_number} isn't clubbed")
    _ensure_clubbable(db, lead)
    order.clubbed_into_id = None


def sync_club_children(db: Session, lead: Order) -> list[tuple[Order, str]]:
    """Copy the lead's status, and once it has an AWB its courier fields, onto
    its clubbed orders.

    Courier fields wait for the AWB: before that the lead's Shiprocket ids are
    its own checkout draft, and copying them makes the parcel look booked.
    Returns (order, previous_status) for each clubbed order whose status moved.
    Caller commits.
    """
    moved: list[tuple[Order, str]] = []
    lead_status = (lead.status or "").lower()
    for child in club_children(db, lead):
        if lead.awb_code:
            child.shiprocket_order_id = lead.shiprocket_order_id
            child.shiprocket_shipment_id = lead.shiprocket_shipment_id
            child.awb_code = lead.awb_code
            child.courier_name = lead.courier_name
            child.tracking_url = lead.tracking_url
            child.pickup_scheduled_date = lead.pickup_scheduled_date
            child.pickup_generated_at = lead.pickup_generated_at
        previous = (child.status or "placed").lower()
        # Cancelling releases stock per order, so it goes through cancel_order_and_parcel.
        if lead_status == "cancelled" or previous in ("cancelled", "delivered"):
            continue
        if previous != lead_status:
            child.status = lead.status
            moved.append((child, previous))
    return moved
