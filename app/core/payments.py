"""Razorpay Standard Checkout helpers (create order + verify signature).

Aligned with the working Pragnameter flow and Razorpay Standard Web Checkout:
create order → Checkout.js modal → HMAC signature verify.
"""

from __future__ import annotations

import razorpay
from razorpay import errors

from app.core.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

# Minimum Razorpay order amount (100 paise = ₹1).
MIN_AMOUNT_PAISE = 100


class RazorpayAuthError(Exception):
    """Raised when Razorpay rejects API credentials."""


class RazorpayOrderError(Exception):
    """Raised when Razorpay order creation fails for non-auth reasons."""


def get_razorpay_credentials() -> tuple[str, str]:
    key_id = (RAZORPAY_KEY_ID or "").strip()
    key_secret = (RAZORPAY_KEY_SECRET or "").strip()
    return key_id, key_secret


def get_client() -> razorpay.Client:
    key_id, key_secret = get_razorpay_credentials()
    if not key_id or not key_secret:
        raise RazorpayAuthError("Razorpay credentials are not configured")
    return razorpay.Client(auth=(key_id, key_secret))


# Module-level client for warm Lambda reuse (credentials read at import).
_key_id, _key_secret = get_razorpay_credentials()
client = razorpay.Client(auth=(_key_id, _key_secret)) if _key_id and _key_secret else None


def create_razorpay_order(
    *,
    amount_paise: int,
    receipt: str,
    notes: dict[str, str] | None = None,
) -> dict:
    """POST https://api.razorpay.com/v1/orders — returns Razorpay order dict."""
    if amount_paise < MIN_AMOUNT_PAISE:
        raise ValueError(f"Minimum amount is {MIN_AMOUNT_PAISE} paise (₹1)")

    rzp = client or get_client()
    payload: dict = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": receipt[:40],  # Razorpay receipt max length
        "payment_capture": 1,
    }
    if notes:
        payload["notes"] = notes

    try:
        return rzp.order.create(payload)
    except errors.BadRequestError as exc:
        if "authentication failed" in str(exc).lower():
            raise RazorpayAuthError(str(exc)) from exc
        raise RazorpayOrderError(str(exc)) from exc
    except errors.ServerError as exc:
        raise RazorpayOrderError(str(exc)) from exc


def verify_payment_signature(
    *,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """HMAC-SHA256(order_id|payment_id, KEY_SECRET) via official SDK."""
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return False
    rzp = client or get_client()
    try:
        rzp.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )
        return True
    except errors.SignatureVerificationError:
        return False


def fetch_payment(razorpay_payment_id: str) -> dict:
    rzp = client or get_client()
    return rzp.payment.fetch(razorpay_payment_id)


__all__ = [
    "MIN_AMOUNT_PAISE",
    "RazorpayAuthError",
    "RazorpayOrderError",
    "client",
    "create_razorpay_order",
    "errors",
    "fetch_payment",
    "get_client",
    "get_razorpay_credentials",
    "verify_payment_signature",
]
