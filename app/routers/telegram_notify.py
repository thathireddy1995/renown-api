"""Enqueue new customer orders to Optimus SQS (Telegram worker).

Checkout is not blocked on Telegram: send_message is a short SQS call, and a
queue failure is logged without failing the order.
"""

from __future__ import annotations

import json
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import AWS_REGION, ORDER_NOTIFY_QUEUE_URL
from app.schemas import Customer, Order

logger = logging.getLogger(__name__)

_sqs = None


def _sqs_client():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs", region_name=AWS_REGION)
    return _sqs


def _format_address(order: Order) -> str:
    if (order.delivery or "").lower() == "pickup" and order.pickup_store:
        store = order.pickup_store
        parts = [f"Pickup · {store.name}"]
        if store.address:
            parts.append(store.address)
        if store.city:
            parts.append(store.city)
        return "\n".join(p for p in parts if p)

    addr = order.address
    if not addr:
        return ""
    parts = [addr.line1]
    if addr.line2:
        parts.append(addr.line2)
    city_line = ", ".join(p for p in [addr.city, addr.state, addr.postal_code] if p)
    if city_line:
        parts.append(city_line)
    if addr.country:
        parts.append(addr.country)
    return "\n".join(p for p in parts if p)


def _phone(order: Order, customer: Customer) -> str:
    if order.address and order.address.phone:
        return order.address.phone
    if customer.phone:
        return customer.phone
    if order.pickup_store and order.pickup_store.phone:
        return order.pickup_store.phone
    return ""


def notify_order_placed(order: Order, customer: Customer) -> None:
    """Snapshot order fields and enqueue them for the Optimus Telegram worker."""
    queue_url = (ORDER_NOTIFY_QUEUE_URL or "").strip()
    if not queue_url:
        logger.warning("Order notify skipped: ORDER_NOTIFY_QUEUE_URL is not set")
        return

    payload = {
        "order_id": order.order_number,
        "customer_name": customer.name or "",
        "total": float(order.total or 0),
        "shipping_charges": float(order.shipping_fee or 0),
        "address": _format_address(order),
        "phone": _phone(order, customer),
        "lines": [
            [
                it.name_snapshot or (it.product.name if it.product else "Item"),
                int(it.qty or 0),
                float(it.price_snapshot or 0),
            ]
            for it in (order.items or [])
        ],
        "payment_method": order.payment_method or "",
        "delivery": order.delivery or "",
        "discount": float(order.discount or 0),
        "coupon_code": order.coupon_code,
    }
    try:
        _sqs_client().send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
        logger.info("Order notify enqueued order_id=%s", payload["order_id"])
    except (BotoCoreError, ClientError):
        logger.exception("Order notify SQS send failed order_id=%s", payload["order_id"])
