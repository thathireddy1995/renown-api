"""Send OTP via MSG91 WhatsApp Authentication template.

Mirrors meta-apis/login_code.py — used by customer registration / password reset.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from app.core import config as app_config

logger = logging.getLogger(__name__)

SEND_URL = "https://api.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/bulk/"

# Hardcoded fallbacks (move to secrets later). Empty env must not break OTP.
_AUTH_KEY = "554114Avcg6BwNFF6a65c35aP1"
_WA_NUMBER = "919642512952"
_WA_TEMPLATE = "verify_user_v1"
_WA_LANG = "en_US"


class WhatsAppOtpError(Exception):
    """Raised when MSG91 rejects or fails to accept an OTP send."""


def _auth_key() -> str:
    return (app_config.MSG91_AUTH_KEY or _AUTH_KEY).strip()


def _wa_number() -> str:
    return (app_config.MSG91_WA_INTEGRATED_NUMBER or _WA_NUMBER).strip()


def _wa_template() -> str:
    return (app_config.MSG91_WA_TEMPLATE_NAME or _WA_TEMPLATE).strip()


def _wa_lang() -> str:
    return (app_config.MSG91_WA_TEMPLATE_LANG or _WA_LANG).strip()


def _wa_namespace() -> str:
    return (app_config.MSG91_WA_NAMESPACE or "").strip()


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
    auth_key = _auth_key()
    integrated_number = _wa_number()
    template_name = _wa_template()
    template_lang = _wa_lang()
    namespace = _wa_namespace()

    if not auth_key:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing MSG91_AUTH_KEY).")
    if not integrated_number:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing sender number).")
    if not template_name:
        raise WhatsAppOtpError("WhatsApp OTP is not configured (missing template name).")

    mobile = to_whatsapp_mobile(phone_10)
    components: dict[str, Any] = {
        "body_1": {"type": "text", "value": code},
        "button_1": {"subtype": "url", "type": "text", "value": code},
    }
    template: dict[str, Any] = {
        "name": template_name,
        "language": {"code": template_lang, "policy": "deterministic"},
        "to_and_components": [{"to": [mobile], "components": components}],
    }
    if namespace:
        template["namespace"] = namespace

    payload = {
        "integrated_number": integrated_number,
        "content_type": "template",
        "payload": {
            "messaging_product": "whatsapp",
            "type": "template",
            "template": template,
        },
    }
    headers = {
        "authkey": auth_key,
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

    # MSG91 often returns status=success with http 200.
    if not (resp.ok and not data.get("hasError")):
        logger.error(
            "MSG91 WhatsApp OTP failed for …%s status=%s body=%s",
            mobile[-4:],
            resp.status_code,
            data,
        )
        raise WhatsAppOtpError(
            "Failed to send OTP via WhatsApp. Please check the number and try again."
        )

    logger.info(
        "WhatsApp OTP accepted by MSG91 for …%s request_id=%s",
        mobile[-4:],
        data.get("request_id"),
    )
    return data
