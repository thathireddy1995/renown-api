"""Shiprocket API client — auth token auto-refreshes on day 9 (token lasts 10 days)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import requests

from app.core.config import SHIPROCKET_EMAIL, SHIPROCKET_PASSWORD

logger = logging.getLogger(__name__)

BASE_URL = "https://apiv2.shiprocket.in/v1/external"
# Shiprocket JWT is valid for 10 days; refresh on day 9 to avoid expiry races.
TOKEN_REFRESH_AFTER_SECONDS = 9 * 24 * 60 * 60

_lock = threading.Lock()
_token: str | None = None
_token_issued_at: float = 0.0


class ShiprocketError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def configured() -> bool:
    return bool(SHIPROCKET_EMAIL and SHIPROCKET_PASSWORD)


def _login() -> str:
    if not configured():
        raise ShiprocketError("Shiprocket credentials are not configured")
    res = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": SHIPROCKET_EMAIL, "password": SHIPROCKET_PASSWORD},
        timeout=30,
    )
    if res.status_code >= 400:
        detail = res.text[:300]
        raise ShiprocketError(f"Shiprocket auth failed: {detail}", res.status_code)
    data = res.json()
    token = data.get("token")
    if not token:
        raise ShiprocketError("Shiprocket auth response missing token")
    return str(token)


def get_token(*, force_refresh: bool = False) -> str:
    """Return a valid Bearer token, refreshing after 9 days (or on force)."""
    global _token, _token_issued_at
    with _lock:
        age = time.time() - _token_issued_at if _token_issued_at else None
        needs = (
            force_refresh
            or not _token
            or age is None
            or age >= TOKEN_REFRESH_AFTER_SECONDS
        )
        if needs:
            _token = _login()
            _token_issued_at = time.time()
            logger.info("Shiprocket token refreshed (valid ~10 days; refresh at day 9)")
        return _token


def _request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json: dict | None = None,
) -> Any:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{BASE_URL}{path}"
    res = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
    if res.status_code in (401, 403):
        token = get_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        res = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
    if res.status_code >= 400:
        raise ShiprocketError(
            f"Shiprocket {method} {path} failed: {res.text[:400]}",
            res.status_code,
        )
    if not res.content:
        return {}
    return res.json()


def track_by_awb(awb_code: str) -> dict[str, Any]:
    """Track shipment by AWB. Returns Shiprocket tracking payload."""
    awb = (awb_code or "").strip()
    if not awb:
        raise ShiprocketError("AWB code is required")
    return _request("GET", f"/courier/track/awb/{awb}")


def list_pickup_locations() -> list[dict[str, Any]]:
    raw = _request("GET", "/settings/company/pickup")
    data = raw.get("data") if isinstance(raw, dict) else raw
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if not isinstance(data, dict):
        return []
    addr = data.get("shipping_address")
    if isinstance(addr, list):
        return [row for row in addr if isinstance(row, dict)]
    if isinstance(addr, dict):
        return [addr]
    recent = data.get("recent_addresses") or []
    if isinstance(recent, list):
        return [row for row in recent if isinstance(row, dict)]
    return []


def add_pickup_location(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _request("POST", "/settings/company/addpickup", json=payload)
    return raw if isinstance(raw, dict) else {}


def create_adhoc_order(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _request("POST", "/orders/create/adhoc", json=payload)
    if not isinstance(raw, dict):
        raise ShiprocketError("Shiprocket create-order returned an empty response")
    body = raw.get("payload") if isinstance(raw.get("payload"), dict) else raw
    status_code = body.get("status_code", raw.get("status_code"))
    if status_code in (0, "0"):
        raise ShiprocketError(
            f"Shiprocket create-order rejected: {body.get('message') or raw.get('message') or raw}"
        )
    order_id = body.get("order_id") or body.get("order_id_str")
    shipment_id = body.get("shipment_id")
    if not shipment_id:
        raise ShiprocketError(f"Shiprocket create-order missing shipment_id: {str(raw)[:300]}")
    return {
        "order_id": str(order_id) if order_id is not None else "",
        "shipment_id": str(shipment_id),
        "awb_code": str(body.get("awb_code") or "") or "",
        "courier_name": str(body.get("courier_name") or "") or "",
        "raw": raw,
    }


def assign_awb(shipment_id: str) -> dict[str, Any]:
    sid = str(shipment_id).strip()
    if not sid:
        raise ShiprocketError("shipment_id is required")
    raw = _request(
        "POST",
        "/courier/assign/awb",
        json={"shipment_id": int(sid) if sid.isdigit() else sid},
    )
    if not isinstance(raw, dict):
        raise ShiprocketError("Shiprocket assign-AWB returned an empty response")
    data = raw
    inner = raw.get("response")
    if isinstance(inner, dict):
        data = inner.get("data") if isinstance(inner.get("data"), dict) else inner
    awb = str(data.get("awb_code") or raw.get("awb_code") or "")
    if not awb:
        raise ShiprocketError(f"Shiprocket assign-AWB missing awb_code: {str(raw)[:300]}")
    return {
        "awb_code": awb,
        "courier_name": str(data.get("courier_name") or raw.get("courier_name") or ""),
        "raw": raw,
    }


def request_pickup(shipment_id: str) -> dict[str, Any]:
    sid = str(shipment_id).strip()
    if not sid:
        raise ShiprocketError("shipment_id is required")
    try:
        numeric = int(sid)
    except ValueError:
        numeric = sid
    raw = _request("POST", "/courier/generate/pickup", json={"shipment_id": [numeric]})
    return raw if isinstance(raw, dict) else {}


# Shiprocket shipment_status integers → Renown keys (when the string is missing).
_SR_STATUS_CODE = {
    3: "packed",
    4: "packed",
    6: "shipped",
    7: "delivered",
    17: "out",
    18: "shipped",
    26: "packed",
    38: "shipped",
    42: "shipped",
}

_STATUS_RANK = {
    "placed": 0,
    "verified": 1,
    "packed": 2,
    "shipped": 3,
    "out": 4,
    "delivered": 5,
}


def map_shiprocket_status(current_status: str | None) -> str:
    """Map Shiprocket status string → Renown order status key. Empty → ''."""
    s = (current_status or "").strip().lower()
    if not s:
        return ""
    if s.isdigit():
        return _SR_STATUS_CODE.get(int(s), "shipped")
    if "undeliver" in s:
        return "shipped"
    if "deliver" in s:
        return "delivered"
    if "out for delivery" in s or s in ("ofd", "out_for_delivery"):
        return "out"
    if any(
        x in s
        for x in (
            "in transit",
            "shipped",
            "picked up",
            "pickup",
            "dispatched",
            "in_transit",
            "rto",
        )
    ):
        return "shipped"
    if "pack" in s or "ready to ship" in s or "label" in s:
        return "packed"
    return "shipped"


def should_advance_status(current: str | None, mapped: str | None) -> bool:
    """True only when courier status is strictly ahead of the Renown status."""
    cur = (current or "").strip().lower()
    nxt = (mapped or "").strip().lower()
    if not nxt or cur in ("cancelled", "canceled"):
        return False
    if cur == nxt:
        return False
    if cur not in _STATUS_RANK or nxt not in _STATUS_RANK:
        return False
    return _STATUS_RANK[nxt] > _STATUS_RANK[cur]


def normalize_tracking(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten Shiprocket track response into a UI-friendly shape."""
    data = payload.get("tracking_data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}

    raw_error = data.get("error")
    if isinstance(raw_error, str):
        error = raw_error.strip()
    elif raw_error:
        error = str(raw_error)
    else:
        error = ""
    track_status = data.get("track_status")
    if error or track_status in (0, "0"):
        msg = error or "Tracking details not found for this AWB."
        return {
            "awb": "",
            "courier": "",
            "current_status": "",
            "origin": "",
            "destination": "",
            "edd": "",
            "track_url": "",
            "activities": [],
            "mapped_status": "",
            "error": msg or "Tracking details not found for this AWB.",
        }

    tracks = data.get("shipment_track") or []
    latest = tracks[0] if isinstance(tracks, list) and tracks else {}
    if not isinstance(latest, dict):
        latest = {}

    activities_raw = data.get("shipment_track_activities") or []
    activities: list[dict[str, str]] = []
    if isinstance(activities_raw, list):
        for a in activities_raw:
            if not isinstance(a, dict):
                continue
            activities.append(
                {
                    "date": str(a.get("date") or a.get("activity_date") or ""),
                    "activity": str(a.get("activity") or a.get("status") or ""),
                    "location": str(a.get("location") or ""),
                }
            )

    current = (
        latest.get("current_status")
        or latest.get("status")
        or latest.get("sr-status-label")
        or ""
    )
    if not current and data.get("shipment_status") is not None:
        current = data.get("shipment_status")

    awb = str(latest.get("awb_code") or latest.get("awb") or data.get("awb") or "")
    track_url = str(data.get("track_url") or latest.get("track_url") or "")
    if not track_url and awb:
        track_url = f"https://shiprocket.co/tracking/{awb}"

    return {
        "awb": awb,
        "courier": str(
            latest.get("courier_name")
            or latest.get("courier")
            or data.get("courier_name")
            or ""
        ),
        "current_status": str(current),
        "origin": str(latest.get("origin") or ""),
        "destination": str(latest.get("destination") or ""),
        "edd": str(latest.get("edd") or latest.get("etd") or ""),
        "track_url": track_url,
        "activities": activities,
        "mapped_status": map_shiprocket_status(str(current)),
        "error": "",
    }
