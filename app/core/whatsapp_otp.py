"""Send OTP via the Meta WhatsApp Cloud API (Authentication template).

Mirrors meta-apis/renown/check_and_send.py — used by passwordless login,
registration, password reset, store-app login and pickup OTPs.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.core import config as app_config

logger = logging.getLogger(__name__)


class WhatsAppOtpError(Exception):
    """Raised when Meta rejects or fails to accept an OTP send."""


def to_whatsapp_mobile(phone_10: str) -> str:
    """DB stores 10-digit IN numbers; Meta expects country code without +."""
    digits = "".join(ch for ch in phone_10 if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return digits
    if len(digits) == 10:
        return f"91{digits}"
    raise WhatsAppOtpError("Enter a valid 10-digit mobile number.")


def send_whatsapp_otp(phone_10: str, code: str) -> dict[str, Any]:
    """
    Send `code` to `phone_10` using the configured WhatsApp auth template.
    Template body: "*{OTP}* is your verification code." + a Copy code button.
    """
    token = app_config.WHATSAPP_ACCESS_TOKEN
    phone_number_id = app_config.WHATSAPP_PHONE_NUMBER_ID
    template_name = app_config.WHATSAPP_OTP_TEMPLATE
    template_lang = app_config.WHATSAPP_OTP_LANG

    if not token:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing WHATSAPP_ACCESS_TOKEN).")
    if not phone_number_id:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing WHATSAPP_PHONE_NUMBER_ID).")
    if not template_name:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing template name).")

    mobile = to_whatsapp_mobile(phone_10)
    url = f"https://graph.facebook.com/{app_config.WHATSAPP_GRAPH_VERSION}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": mobile,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_lang},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": code}],
                },
            ],
        },
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as exc:
        logger.exception("WhatsApp OTP request failed for …%s", mobile[-4:])
        raise WhatsAppOtpError("Unable to send OTP right now. Please try again.") from exc

    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    if not resp.ok or "error" in data or not data.get("messages"):
        err = data.get("error") if isinstance(data.get("error"), dict) else {}
        logger.error(
            "WhatsApp OTP failed for …%s status=%s code=%s message=%s",
            mobile[-4:],
            resp.status_code,
            err.get("code"),
            err.get("message") or data,
        )
        raise WhatsAppOtpError(
            "Failed to send OTP via WhatsApp. Please check the number and try again."
        )

    logger.info(
        "WhatsApp OTP accepted by Meta for …%s message_id=%s",
        mobile[-4:],
        data["messages"][0].get("id"),
    )
    return data
