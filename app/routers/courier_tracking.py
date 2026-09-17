"""Inbound courier tracking webhook (Shiprocket → Renown).

The path must not contain "shiprocket", "kartrocket", "sr" or "kr": Shiprocket
blocks webhook URLs containing those keywords, so this is deliberately named
after the generic capability instead of the vendor.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import SHIPROCKET_WEBHOOK_TOKEN
from app.core.courier_status import apply_tracking_update
from app.database import get_db
from app.dto.courier_dto import CourierTrackingAck, CourierTrackingWebhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courier", tags=["courier"])


@router.post("/tracking-update", response_model=CourierTrackingAck)
def tracking_update(
    payload: CourierTrackingWebhook,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
) -> CourierTrackingAck:
    """Advance an order's status from a courier scan event.

    Returns 200 for any authenticated call, including payloads that match no
    order or that we decline to apply — Shiprocket retries non-2xx responses
    and disables webhooks that keep failing.
    """
    if not SHIPROCKET_WEBHOOK_TOKEN:
        # Fail closed: this endpoint writes order status, so it must never be
        # reachable without a configured secret.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Courier webhook is not configured.",
        )
    if not x_api_key or not secrets.compare_digest(
        x_api_key, SHIPROCKET_WEBHOOK_TOKEN
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook credentials.",
        )

    body = payload.model_dump()
    result = apply_tracking_update(db, body)
    if not result.get("matched"):
        # Logged without the payload: it carries the customer's address.
        logger.warning(
            "courier webhook matched no order: awb=%s sr_order_id=%s order_id=%s",
            body.get("awb") or body.get("awb_code"),
            body.get("sr_order_id"),
            body.get("order_id"),
        )
    return CourierTrackingAck(**result)
