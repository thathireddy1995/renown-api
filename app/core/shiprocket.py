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


def _request(method: str, path: str, *, params: dict | None = None) -> Any:
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{BASE_URL}{path}"
    res = requests.request(method, url, headers=headers, params=params, timeout=30)
    if res.status_code in (401, 403):
        token = get_token(force_refresh=True)
        headers["Authorization"] = f"Bearer {token}"
        res = requests.request(method, url, headers=headers, params=params, timeout=30)
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


def map_shiprocket_status(current_status: str | None) -> str:
    """Map Shiprocket status string → Renown order status key."""
    s = (current_status or "").strip().lower()
    if not s:
        return "shipped"
    if "deliver" in s and "undeliver" not in s:
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


def normalize_tracking(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten Shiprocket track response into a UI-friendly shape."""
    data = payload.get("tracking_data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}

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
        or data.get("shipment_status")
        or ""
    )
    return {
        "awb": str(latest.get("awb_code") or latest.get("awb") or ""),
        "courier": str(latest.get("courier_name") or latest.get("courier") or ""),
        "current_status": str(current),
        "origin": str(latest.get("origin") or ""),
        "destination": str(latest.get("destination") or ""),
        "edd": str(latest.get("edd") or latest.get("etd") or ""),
        "track_url": str(data.get("track_url") or latest.get("track_url") or ""),
        "activities": activities,
        "mapped_status": map_shiprocket_status(str(current)),
    }
