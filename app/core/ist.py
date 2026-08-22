"""India Standard Time is the only clock this API uses."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, text
from sqlalchemy.types import TypeDecorator

IST = ZoneInfo("Asia/Kolkata")
IST_SQL_NOW = text("(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')")


class ISTDateTime(TypeDecorator):
    """Naive timestamp stored and read as India Standard Time."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, _dialect):
        if value is None or not isinstance(value, datetime):
            return value
        return to_naive(value)


def now() -> datetime:
    return datetime.now(IST)


def naive_now() -> datetime:
    return now().replace(tzinfo=None)


def today() -> date:
    return now().date()


def as_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt.astimezone(IST)


def to_naive(dt: datetime) -> datetime:
    return as_ist(dt).replace(tzinfo=None)


def start_of_day(dt: datetime | date | None = None) -> datetime:
    if dt is None:
        local = now()
    elif isinstance(dt, datetime):
        local = as_ist(dt)
    else:
        return datetime.combine(dt, time.min)
    return local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def end_of_day(dt: datetime | date | None = None) -> datetime:
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return datetime.combine(dt, time.max)
    local = start_of_day(dt)
    return local.replace(hour=23, minute=59, second=59, microsecond=999999)


def format_ist_date(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return as_ist(dt).strftime("%Y-%m-%d")


def format_ist_datetime(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return as_ist(dt).strftime("%Y-%m-%d %H:%M")
