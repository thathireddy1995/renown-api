"""Send OTP via MSG91 WhatsApp Authentication template.

Mirrors meta-apis/login_code.py — used by customer registration / password reset.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.core.config import (
    MSG91_AUTH_KEY,
    MSG91_WA_INTEGRATED_NUMBER,
    MSG91_WA_NAMESPACE,
    MSG91_WA_TEMPLATE_LANG,
    MSG91_WA_TEMPLATE_NAME,
)

logger = logging.getLogger(__name__)

SEND_URL = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"


class WhatsAppOtpError(Exception):
    """Raised when MSG91 rejects or fails to accept an OTP send."""


def to_whatsapp_mobile(phone_10: str) -> str:
    """DB stores 10-digit IN numbers; MSG91 expects country code without +."""
    digits = "".join(ch for ch in phone_10 if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return digits
    if len(digits) == 10:
        return f"91{digits}"
    raise WhatsAppOtpError("Enter a valid 10-digit mobile number.")


def send_whatsapp_otp(phone_10: str, code: str) -> dict[str, Any]:
    """
    Send `code` to `phone_10` using the configured WhatsApp auth template.
    Template body: "{OTP} is your verification code."
    """
    if not MSG91_AUTH_KEY:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing MSG91_AUTH_KEY).")
    if not MSG91_WA_INTEGRATED_NUMBER:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing sender number).")
    if not MSG91_WA_TEMPLATE_NAME:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing template name).")

    mobile = to_whatsapp_mobile(phone_10)
    components: dict[str, Any] = {
        "body_1": {"type": "text", "value": code},
        "button_1": {"subtype": "url", "type": "text", "value": code},
    }
    template: dict[str, Any] = {
        "name": MSG91_WA_TEMPLATE_NAME,
        "language": {"code": MSG91_WA_TEMPLATE_LANG, "policy": "deterministic"},
        "to_and_components": [{"to": [mobile], "components": components}],
    }
    if MSG91_WA_NAMESPACE:
        template["namespace"] = MSG91_WA_NAMESPACE

    payload = {
        "integrated_number": MSG91_WA_INTEGRATED_NUMBER,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": template,
        },
    }
    headers = {
        "authkey": MSG91_AUTH_KEY,
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    try:
        resp = requests.post(SEND_URL, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        logger.exception("MSG91 WhatsApp OTP request failed for …%s", mobile[-4:])
        raise WhatsAppOtpError("Unable to send OTP right now. Please try again.") from exc

    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    ok = resp.ok and not data.get("hasError") and str(data.get("status", "")).lower() in {
        "success",
        "",
    }
    # MSG91 often returns status=success with http 200; treat other 2xx without hasError as ok.
    if resp.ok and not data.get("hasError"):
        ok = True

    if not ok:
        logger.error(
            "MSG91 WhatsApp OTP failed for …%s status=%s body=%s",
            mobile[-4:],
            resp.status_code,
            data,
        )
        raise WhatsAppOtpError(
            "Failed to send OTP via WhatsApp. Please check the number and try again."
        )

    logger.info("WhatsApp OTP accepted by MSG91 for …%s request_id=%s", mobile[-4:], data.get("request_id"))
    return data
