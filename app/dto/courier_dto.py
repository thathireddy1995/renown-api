"""Courier (Shiprocket) tracking webhook I/O models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CourierTrackingWebhook(BaseModel):
    """Body of a Shiprocket tracking webhook.

    Shiprocket sends a superset of these keys and the exact shape varies by
    courier and event, so extras are kept rather than rejected — a 422 here
    would make Shiprocket retry a payload we can never accept. Numeric ids
    arrive as either int or string depending on the event.
    """

    model_config = ConfigDict(extra="allow")

    awb: str | int | None = None
    awb_code: str | int | None = None

    current_status: str | None = None
    current_status_id: str | int | None = None
    shipment_status: str | int | None = None
    shipment_status_id: str | int | None = None
    status: str | int | None = None

    order_id: str | int | None = None
    channel_order_id: str | int | None = None
    sr_order_id: str | int | None = None
    shipment_id: str | int | None = None

    courier_name: str | None = None
    etd: str | None = None
    current_timestamp: str | None = None
    is_return: bool | int | None = None


class CourierTrackingAck(BaseModel):
    """Acknowledgement returned to Shiprocket.

    Always HTTP 200 once authenticated, including for payloads we chose not to
    apply: a non-2xx makes Shiprocket retry and can get the webhook disabled.
    """

    received: bool = True
    matched: bool = False
    order_number: str | None = None
    status: str | None = None
    changed: bool = False
    detail: str | None = None
