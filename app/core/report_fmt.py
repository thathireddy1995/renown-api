"""Shared formatting helpers for report KPIs."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def start_of_day(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def inr(amount: Decimal | float | int | None) -> str:
    if amount is None:
        return "₹0"
    n = int(round(float(amount)))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        body = s
    else:
        body = s[-3:]
        s = s[:-3]
        while s:
            body = s[-2:] + "," + body
            s = s[:-2]
    return f"{sign}₹{body}"


def inr_lakhs(amount: Decimal | float | int | None) -> str:
    n = float(amount or 0) / 100_000.0
    return f"₹{n:.1f}L"


def pct(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}%"


def delta_pct(current: float, previous: float) -> str:
    if previous == 0:
        return "+0%" if current == 0 else "+100%"
    change = ((current - previous) / abs(previous)) * 100
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


def delta_count(current: int | float, previous: int | float, suffix: str = "") -> str:
    diff = current - previous
    sign = "+" if diff >= 0 else ""
    if isinstance(diff, float) and not diff.is_integer():
        body = f"{sign}{diff:.1f}"
    else:
        body = f"{sign}{int(diff)}"
    return f"{body}{suffix}"


def weekday_label(d: date) -> str:
    return d.strftime("%a")


def month_label(d: date) -> str:
    return d.strftime("%b")
