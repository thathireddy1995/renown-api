"""Order messages to customers over the Meta WhatsApp Cloud API.

Two Utility templates (WhatsApp Manager):
  order_placed — body {{1}} name, {{2}} order no, {{3}} amount, {{4}} payment;
                 URL button suffix {{1}} = "<order no>&inv=<invoice token>".
  order_update — body {{1}} name, {{2}} order no, {{3}} status, {{4}} message;
                 URL button suffix {{1}} = "<order no>&inv=<invoice token>".

Sends never raise: an order or status change must not fail because WhatsApp
did. Call these only after the DB commit so a rollback cannot leave the
customer with a message about a change that never happened.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import requests

from app.core import config as app_config
from app.core.whatsapp_otp import WhatsAppOtpError, to_whatsapp_mobile
from app.schemas import Customer, Order, StoreOrder

logger = logging.getLogger(__name__)


def _clean_param(value: str) -> str:
    # Meta rejects template params with newlines, tabs or 4+ consecutive spaces.
    return " ".join(str(value).split()) or "-"


def _first_name(name: str | None) -> str:
    parts = (name or "").split()
    return parts[0] if parts else "there"


def _amount(value: Decimal | float | int | None) -> str:
    total = float(value or 0)
    return f"{total:,.0f}" if total == int(total) else f"{total:,.2f}"


def track_link_suffix(order_number: str, invoice_token: str | None) -> str:
    """URL button suffix after .../track-order?id= — the invoice token lets the
    customer open the order and invoice from WhatsApp without signing in."""
    return f"{order_number}&inv={invoice_token}" if invoice_token else order_number


def _send_template(
    phone: str | None,
    template: str,
    body: list[str],
    order_number: str,
    invoice_token: str | None = None,
) -> bool:
    if not app_config.WHATSAPP_ORDER_NOTIFY:
        return False
    token = app_config.WHATSAPP_ACCESS_TOKEN
    phone_number_id = app_config.WHATSAPP_PHONE_NUMBER_ID
    if not token or not phone_number_id or not template:
        logger.warning("WhatsApp order message skipped (%s): not configured", order_number)
        return False
    try:
        mobile = to_whatsapp_mobile(phone or "")
    except WhatsAppOtpError:
        logger.warning("WhatsApp order message skipped (%s): no valid phone", order_number)
        return False

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": mobile,
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": app_config.WHATSAPP_ORDER_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": _clean_param(p)} for p in body],
                },
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [
                        {"type": "text", "text": track_link_suffix(order_number, invoice_token)}
                    ],
                },
            ],
        },
    }
    url = f"https://graph.facebook.com/{app_config.WHATSAPP_GRAPH_VERSION}/{phone_number_id}/messages"
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
            timeout=10,
        )
        data = resp.json() if resp.content else {}
    except (requests.RequestException, ValueError):
        logger.exception("WhatsApp %s request failed (%s)", template, order_number)
        return False

    if not resp.ok or not data.get("messages"):
        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        logger.error(
            "WhatsApp %s failed (%s) status=%s code=%s message=%s",
            template,
            order_number,
            resp.status_code,
            err.get("code"),
            err.get("message") or data,
        )
        return False

    logger.info(
        "WhatsApp %s sent (%s) to …%s message_id=%s",
        template,
        order_number,
        mobile[-4:],
        data["messages"][0].get("id"),
    )
    return True


def _order_phone(order: Order, customer: Customer | None) -> str | None:
    if customer and customer.phone:
        return customer.phone
    if order.address and order.address.phone:
        return order.address.phone
    return None


def _payment_label(order: Order) -> str:
    if (order.payment_status or "").lower() == "paid":
        return "Paid online"
    if (order.payment_method or "").lower() == "cod":
        return "Cash on Delivery"
    return (order.payment_method or "Pending").title()


def send_order_placed(order: Order, customer: Customer) -> bool:
    return _send_template(
        _order_phone(order, customer),
        app_config.WHATSAPP_ORDER_PLACED_TEMPLATE,
        [
            _first_name(customer.name),
            order.order_number,
            _amount(order.total),
            _payment_label(order),
        ],
        order.order_number,
        order.verify_token,
    )


def send_store_order_placed(order: StoreOrder, invoice_token: str) -> bool:
    """order_placed for an order a store manager placed on the customer's behalf."""
    method = (order.payment_method or "cash").lower()
    method_label = {"upi": "UPI", "card": "Card", "cash": "Cash", "online": "Online"}.get(method, method.title())
    store = order.store.name if order.store else "store"
    return _send_template(
        order.customer_phone,
        app_config.WHATSAPP_ORDER_PLACED_TEMPLATE,
        [
            _first_name(order.customer_name),
            order.order_number,
            _amount(order.total),
            f"Paid at {store} ({method_label})",
        ],
        order.order_number,
        invoice_token,
    )


def _online_update(order: Order) -> tuple[str, str] | None:
    """(status label, one-line message) for an online order status, or None to stay silent."""
    key = (order.status or "").lower()
    paid = (order.payment_status or "").lower() == "paid"
    if key == "verified":
        return (
            "Prescription Verified",
            "Your prescription has been verified and your lenses are being prepared.",
        )
    if key == "packed":
        return (
            "Packed",
            "Your order has been packed and will be handed to our delivery partner soon.",
        )
    if key == "shipped":
        message = "Your order has been shipped"
        if order.courier_name:
            message += f" via {order.courier_name}"
        message += "."
        if order.awb_code:
            message += f" Tracking number: {order.awb_code}."
        return ("Shipped", message)
    if key == "out":
        message = "Your order is out for delivery today. Please keep your phone reachable."
        if not paid:
            message += f" Amount to pay on delivery: ₹{_amount(order.total)}."
        return ("Out for Delivery", message)
    if key == "delivered":
        return (
            "Delivered",
            "Your order has been delivered. We hope you love your new eyewear!",
        )
    if key == "cancelled":
        if paid:
            message = (
                "Your order has been cancelled. The amount paid will be refunded to your "
                "original payment method in 5-7 business days."
            )
        else:
            message = "Your order has been cancelled. No payment was charged."
        return ("Cancelled", message)
    return None


def notify_order_status(order: Order, previous_status: str | None) -> bool:
    """Send order_update when an online order moved to a customer-facing status."""
    if (order.status or "").lower() == (previous_status or "").lower():
        return False
    update = _online_update(order)
    if not update:
        return False
    customer = order.customer
    label, message = update
    return _send_template(
        _order_phone(order, customer),
        app_config.WHATSAPP_ORDER_UPDATE_TEMPLATE,
        [_first_name(customer.name if customer else None), order.order_number, label, message],
        order.order_number,
        order.verify_token,
    )


def _store_update(order: StoreOrder) -> tuple[str, str] | None:
    key = (order.status or "").lower()
    store = order.store.name if order.store else "our store"
    pickup = (order.channel or "") == "click_collect"
    if key == "preparing":
        return ("Being Prepared", f"Your order is being prepared at {store}.")
    if key == "ready":
        if not pickup:
            return (
                "Ready for Dispatch",
                f"Your order is ready at {store} and will be delivered to you soon.",
            )
        return (
            "Ready for Pickup",
            f"Your order is ready for pickup at {store}. "
            "Please show the OTP we send you at the counter to collect it.",
        )
    if key in ("collected", "delivered"):
        if not pickup:
            return ("Delivered", "Your order has been delivered. We hope you love your new eyewear!")
        return (
            "Collected",
            f"Your order has been collected from {store}. We hope you love your new eyewear!",
        )
    if key == "cancelled":
        return ("Cancelled", "Your order has been cancelled.")
    return None


def notify_store_order_status(
    order: StoreOrder, previous_status: str | None, invoice_token: str | None = None
) -> bool:
    """Send order_update for store orders that belong to a customer
    (click & collect from the website, or counter orders placed for them)."""
    if (order.channel or "") not in ("click_collect", "home_delivery"):
        return False
    if (order.status or "").lower() == (previous_status or "").lower():
        return False
    update = _store_update(order)
    if not update:
        return False
    label, message = update
    return _send_template(
        order.customer_phone,
        app_config.WHATSAPP_ORDER_UPDATE_TEMPLATE,
        [_first_name(order.customer_name), order.order_number, label, message],
        order.order_number,
        invoice_token,
    )
