"""Apply a courier tracking payload to an order.

Shared by the Shiprocket webhook. The customer tracking endpoint performs the
same status advance inline after polling the courier, so both paths agree on
map_shiprocket_status()/should_advance_status() as the single rule for
"is this courier status ahead of ours".
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.shiprocket import map_shiprocket_status, should_advance_status
from app.schemas import Order

logger = logging.getLogger(__name__)

# map_shiprocket_status() falls back to "shipped" for any label it does not
# recognise, which is fine while a parcel moves forward but wrong for the
# terminal/reverse states below: a cancellation or an RTO would otherwise
# advance a waiting order to "shipped". These need a human, so the webhook
# records courier metadata and leaves status alone.
_NEEDS_MANUAL_REVIEW = (
    "cancel",
    "rto",
    "return",
    "lost",
    "damage",
    "destroy",
    "undeliver",
)


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def resolve_order(db: Session, payload: dict[str, Any]) -> Order | None:
    """Find the order a tracking payload refers to.

    AWB first: it is indexed and identifies the physical shipment. The
    Shiprocket ids are fallbacks for events raised before an AWB exists.
    `order_id` is Shiprocket's channel order id, which is our order_number for
    shipments we booked, so it is checked last — it is the easiest to collide.
    """
    lookups = (
        (Order.awb_code, payload.get("awb") or payload.get("awb_code")),
        (Order.shiprocket_order_id, payload.get("sr_order_id")),
        (Order.shiprocket_shipment_id, payload.get("shipment_id")),
        (
            Order.order_number,
            payload.get("channel_order_id") or payload.get("order_id"),
        ),
    )
    for column, raw in lookups:
        value = _clean(raw)
        if not value:
            continue
        order = db.scalar(select(Order).where(column == value))
        if order:
            return order
    return None


def courier_status_label(payload: dict[str, Any]) -> str:
    """The most descriptive courier status string in the payload."""
    for key in ("current_status", "shipment_status", "status"):
        label = _clean(payload.get(key))
        # Skip bare numbers here so the text keys win over id keys.
        if label and not label.isdigit():
            return label
    for key in ("current_status_id", "shipment_status_id", "shipment_status", "status"):
        label = _clean(payload.get(key))
        if label:
            return label
    return ""


def apply_tracking_update(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Advance an order from a courier tracking payload. Commits when changed."""
    order = resolve_order(db, payload)
    if not order:
        return {"matched": False, "detail": "No order matched this shipment."}

    result: dict[str, Any] = {
        "matched": True,
        "order_number": order.order_number,
        "status": order.status,
        "changed": False,
        "detail": None,
    }

    label = courier_status_label(payload)
    lowered = label.lower()
    dirty = False

    # Courier metadata is safe to backfill regardless of the status decision.
    courier = _clean(payload.get("courier_name"))
    if courier and not order.courier_name:
        order.courier_name = courier[:120]
        dirty = True
    awb = _clean(payload.get("awb") or payload.get("awb_code"))
    if awb and not order.awb_code:
        order.awb_code = awb[:80]
        dirty = True
    if awb and not order.tracking_url:
        order.tracking_url = f"https://shiprocket.co/tracking/{awb}"
        dirty = True

    if payload.get("is_return"):
        result["detail"] = "Return shipment; forward status left unchanged."
    elif any(word in lowered for word in _NEEDS_MANUAL_REVIEW):
        result["detail"] = f"Status '{label}' needs manual review; not applied."
        logger.warning(
            "courier webhook needs review: order=%s courier_status=%s",
            order.order_number,
            label,
        )
    else:
        mapped = map_shiprocket_status(label)
        if should_advance_status(order.status, mapped):
            order.status = mapped
            result["status"] = mapped
            result["changed"] = True
            dirty = True
        else:
            result["detail"] = f"Status '{label}' is not ahead of '{order.status}'."

    if dirty:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "courier webhook commit failed: order=%s", order.order_number
            )
            raise
    return result
