import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AnalyticsEventName = Literal[
    "pageview",
    "click",
    "add_to_cart",
    "begin_checkout",
    "purchase",
]


class TrackAnalyticsIn(BaseModel):
    event_name: AnalyticsEventName = "pageview"
    path: str = Field(default="/", max_length=500)
    referrer: str | None = Field(default=None, max_length=1000)
    timezone: str | None = Field(default=None, max_length=80)
    visitor_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    session_id: str | None = Field(
        default=None,
        min_length=16,
        max_length=32,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    metadata: dict | None = None

    @field_validator("metadata")
    @classmethod
    def limit_metadata(cls, value: dict | None) -> dict | None:
        if value is not None and len(json.dumps(value, default=str).encode("utf-8")) > 4096:
            raise ValueError("Analytics metadata must be 4 KB or smaller")
        return value


class TrackAnalyticsOut(BaseModel):
    ok: bool = True


class AnalyticsCount(BaseModel):
    label: str
    value: int
    pct: float = 0


class AnalyticsPoint(BaseModel):
    date: str
    visitors: int
    pageviews: int
    carts: int
    orders: int


class AnalyticsFunnelStep(BaseModel):
    label: str
    value: int
    pct: float


class WebAnalyticsOut(BaseModel):
    range_days: int
    pageviews: int
    visitors: int
    carts: int
    orders: int
    conversion_pct: float
    bounce_rate_pct: float
    avg_visit_seconds: int
    series: list[AnalyticsPoint]
    funnel: list[AnalyticsFunnelStep]
    top_pages: list[AnalyticsCount]
    top_countries: list[AnalyticsCount]
    devices: list[AnalyticsCount]
    top_events: list[AnalyticsCount]
    top_referrers: list[AnalyticsCount]
