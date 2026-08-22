"""Cookieless visitor identity, device, and country for storefront analytics."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import timedelta
from typing import Any
from uuid import uuid4

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import JWT_SECRET
from app.core.ist import naive_now
from app.schemas import WebAnalyticsEvent

_EVENT_NAME = re.compile(r"^[a-z0-9_]{1,40}$")

_TZ_COUNTRY = {
    "Asia/Kolkata": "IN",
    "Asia/Calcutta": "IN",
    "America/New_York": "US",
    "America/Chicago": "US",
    "America/Denver": "US",
    "America/Los_Angeles": "US",
    "Europe/London": "GB",
    "Europe/Paris": "FR",
    "Europe/Berlin": "DE",
    "Asia/Dubai": "AE",
    "Asia/Singapore": "SG",
    "Asia/Tokyo": "JP",
    "Australia/Sydney": "AU",
}

COUNTRY_NAMES = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "AE": "United Arab Emirates",
    "SG": "Singapore",
    "DE": "Germany",
    "FR": "France",
    "AU": "Australia",
    "JP": "Japan",
    "CA": "Canada",
}


def normalize_event_name(name: str) -> str:
    cleaned = (name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not _EVENT_NAME.match(cleaned):
        return "pageview"
    return cleaned


def normalize_path(path: str) -> str:
    text = (path or "/").split("?", 1)[0].split("#", 1)[0].strip() or "/"
    if len(text) > 500:
        text = text[:500]
    if text != "/" and text.endswith("/"):
        text = text.rstrip("/")
    return text or "/"


def parse_device(user_agent: str | None) -> str:
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    if "mobile" in ua or "iphone" in ua or ("android" in ua and "tablet" not in ua):
        return "mobile"
    return "desktop"


def _first_ip(value: str | None) -> str | None:
    if not value:
        return None
    for part in value.split(","):
        candidate = part.strip().strip("[]")
        if candidate.lower().startswith("for="):
            candidate = candidate.split("=", 1)[1].strip().strip('"').strip("[]")
            candidate = candidate.split(";", 1)[0].strip()
        if ":" in candidate and candidate.count(":") == 1 and "." in candidate:
            candidate = candidate.rsplit(":", 1)[0]
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return None


def client_ip(request: Request) -> str:
    for header in ("x-forwarded-for", "x-real-ip", "forwarded"):
        ip = _first_ip(request.headers.get(header))
        if ip:
            return ip
    host = request.client.host if request.client else None
    return _first_ip(host or "") or "0.0.0.0"


def visitor_hash(ip: str, anonymous_id: str | None = None) -> str:
    # A first-party random browser id distinguishes shoppers sharing a NAT/IP.
    # It is salted and hashed before storage; IP is only a fallback for clients
    # that block local storage or do not yet send the id.
    identity = anonymous_id or ip
    payload = f"{identity}|renown-web|{JWT_SECRET}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def resolve_country(request: Request, timezone_name: str | None) -> str | None:
    for header in (
        "cloudfront-viewer-country",
        "cf-ipcountry",
        "x-country-code",
        "x-appengine-country",
    ):
        raw = (request.headers.get(header) or "").strip().upper()
        if len(raw) == 2 and raw.isalpha() and raw not in {"XX", "T1"}:
            return raw
    tz = (timezone_name or "").strip()
    return _TZ_COUNTRY.get(tz)


def sanitize_referrer(referrer: str | None, host: str | None) -> str | None:
    raw = (referrer or "").strip()
    if not raw:
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(raw)
        ref_host = (parsed.hostname or "").lower().removeprefix("www.")
        current_raw = (host or "").strip()
        current_host = (
            urlparse(current_raw).hostname
            if "://" in current_raw
            else current_raw.split(":", 1)[0]
        )
        current = (current_host or "").lower().removeprefix("www.")
        if not ref_host or (current and (ref_host == current or ref_host.endswith("." + current))):
            return None
        return ref_host[:255]
    except ValueError:
        return None


def session_id_for(db: Session, visitor: str) -> str:
    cutoff = naive_now() - timedelta(minutes=30)
    previous = db.scalar(
        select(WebAnalyticsEvent.session_id)
        .where(
            WebAnalyticsEvent.visitor_hash == visitor,
            WebAnalyticsEvent.created_at >= cutoff,
        )
        .order_by(WebAnalyticsEvent.created_at.desc())
        .limit(1)
    )
    return previous or uuid4().hex[:16]


def record_event(
    db: Session,
    request: Request,
    *,
    event_name: str,
    path: str,
    referrer: str | None,
    timezone_name: str | None,
    anonymous_id: str | None,
    client_session_id: str | None,
    metadata: dict[str, Any] | None,
) -> WebAnalyticsEvent:
    ip = client_ip(request)
    visitor = visitor_hash(ip, anonymous_id)
    row = WebAnalyticsEvent(
        visitor_hash=visitor,
        session_id=client_session_id or session_id_for(db, visitor),
        event_name=normalize_event_name(event_name),
        path=normalize_path(path),
        referrer=sanitize_referrer(referrer, request.headers.get("origin") or request.url.hostname),
        country=resolve_country(request, timezone_name),
        device=parse_device(request.headers.get("user-agent")),
        metadata_=metadata if isinstance(metadata, dict) else {},
    )
    db.add(row)
    db.commit()
    return row
