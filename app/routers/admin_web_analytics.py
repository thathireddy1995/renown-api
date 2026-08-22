"""Admin web analytics dashboard reads."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.web_analytics import COUNTRY_NAMES
from app.database import get_db
from app.dto.web_analytics_dto import (
    AnalyticsCount,
    AnalyticsFunnelStep,
    AnalyticsPoint,
    WebAnalyticsOut,
)

router = APIRouter(
    prefix="/admin/web-analytics",
    tags=["admin-web-analytics"],
    dependencies=[Depends(require_role("admin"))],
)

_STATS_SQL = text(
    """
    WITH bounds AS (
        SELECT now() - make_interval(days => :days) AS since
    ),
    scoped AS (
        SELECT visitor_hash, event_name, path, referrer, country, device, created_at
        FROM web_analytics_events, bounds
        WHERE created_at >= bounds.since
    ),
    series AS (
        SELECT
            day,
            to_char(day, 'Mon DD') AS date,
            visitors,
            pageviews,
            carts,
            orders
        FROM (
            SELECT
                date_trunc('day', created_at)::date AS day,
                count(DISTINCT visitor_hash) AS visitors,
                count(*) FILTER (WHERE event_name = 'pageview') AS pageviews,
                count(DISTINCT visitor_hash) FILTER (WHERE event_name = 'add_to_cart') AS carts,
                count(*) FILTER (WHERE event_name = 'purchase') AS orders
            FROM scoped
            GROUP BY 1
        ) daily
    ),
    home AS (
        SELECT visitor_hash, min(created_at) AS t
        FROM scoped
        WHERE event_name = 'pageview' AND path = '/'
        GROUP BY visitor_hash
    ),
    cart AS (
        SELECT e.visitor_hash, min(e.created_at) AS t
        FROM scoped e
        JOIN home h ON h.visitor_hash = e.visitor_hash AND e.created_at >= h.t
        WHERE e.event_name = 'add_to_cart'
        GROUP BY e.visitor_hash
    ),
    purchase AS (
        SELECT e.visitor_hash
        FROM scoped e
        JOIN cart c ON c.visitor_hash = e.visitor_hash AND e.created_at >= c.t
        WHERE e.event_name = 'purchase'
        GROUP BY e.visitor_hash
    ),
    pages AS (
        SELECT path AS label, count(*)::int AS value
        FROM scoped
        WHERE event_name = 'pageview'
        GROUP BY path
        ORDER BY value DESC
        LIMIT 8
    ),
    countries AS (
        SELECT coalesce(nullif(country, ''), 'UN') AS label, count(DISTINCT visitor_hash)::int AS value
        FROM scoped
        GROUP BY 1
        ORDER BY value DESC
        LIMIT 8
    ),
    devices AS (
        SELECT device AS label, count(DISTINCT visitor_hash)::int AS value
        FROM scoped
        GROUP BY device
        ORDER BY value DESC
    ),
    events AS (
        SELECT event_name AS label, count(*)::int AS value
        FROM scoped
        WHERE event_name <> 'pageview'
        GROUP BY event_name
        ORDER BY value DESC
        LIMIT 8
    ),
    referrers AS (
        SELECT coalesce(referrer, 'Direct') AS label, count(DISTINCT visitor_hash)::int AS value
        FROM scoped
        WHERE event_name = 'pageview'
        GROUP BY 1
        ORDER BY value DESC
        LIMIT 8
    )
    SELECT
        (SELECT count(*) FROM scoped WHERE event_name = 'pageview')::int AS pageviews,
        (SELECT count(DISTINCT visitor_hash) FROM scoped)::int AS visitors,
        (
            SELECT count(DISTINCT visitor_hash)
            FROM scoped
            WHERE event_name = 'add_to_cart'
        )::int AS carts,
        (SELECT count(*) FROM scoped WHERE event_name = 'purchase')::int AS orders,
        coalesce((
            SELECT json_agg(json_build_object(
                'date', date,
                'visitors', visitors,
                'pageviews', pageviews,
                'carts', carts,
                'orders', orders
            ) ORDER BY day)
            FROM series
        ), '[]'::json) AS series,
        (SELECT count(*) FROM home)::int AS funnel_home,
        (SELECT count(*) FROM cart)::int AS funnel_cart,
        (SELECT count(*) FROM purchase)::int AS funnel_orders,
        coalesce((SELECT json_agg(pages ORDER BY value DESC) FROM pages), '[]'::json) AS top_pages,
        coalesce((SELECT json_agg(countries ORDER BY value DESC) FROM countries), '[]'::json) AS top_countries,
        coalesce((SELECT json_agg(devices ORDER BY value DESC) FROM devices), '[]'::json) AS devices,
        coalesce((SELECT json_agg(events ORDER BY value DESC) FROM events), '[]'::json) AS top_events,
        coalesce((SELECT json_agg(referrers ORDER BY value DESC) FROM referrers), '[]'::json) AS top_referrers
    """
)


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round(part * 100 / whole, 1)


def _as_rows(value) -> list[dict]:
    if not value:
        return []
    if isinstance(value, str):
        from json import loads

        value = loads(value)
    return [row for row in value if isinstance(row, dict)]


def _counts(rows: list[dict] | None) -> list[AnalyticsCount]:
    items = rows or []
    total = sum(int(row.get("value") or 0) for row in items) or 1
    return [
        AnalyticsCount(
            label=str(row.get("label") or "Unknown"),
            value=int(row.get("value") or 0),
            pct=_pct(int(row.get("value") or 0), total),
        )
        for row in items
    ]


def _country_counts(rows: list[dict] | None) -> list[AnalyticsCount]:
    items = rows or []
    total = sum(int(row.get("value") or 0) for row in items) or 1
    out: list[AnalyticsCount] = []
    for row in items:
        code = str(row.get("label") or "UN")
        label = COUNTRY_NAMES.get(code, "Unknown" if code in {"UN", "XX"} else code)
        value = int(row.get("value") or 0)
        out.append(AnalyticsCount(label=label, value=value, pct=_pct(value, total)))
    return out


@router.get("", response_model=WebAnalyticsOut)
def web_analytics(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> WebAnalyticsOut:
    row = db.execute(_STATS_SQL, {"days": days}).mappings().one()
    home = int(row["funnel_home"] or 0)
    carts = int(row["funnel_cart"] or 0)
    orders = int(row["funnel_orders"] or 0)
    visitors = int(row["visitors"] or 0)
    series_raw = _as_rows(row["series"])
    return WebAnalyticsOut(
        range_days=days,
        pageviews=int(row["pageviews"] or 0),
        visitors=visitors,
        carts=int(row["carts"] or 0),
        orders=orders,
        conversion_pct=_pct(orders, home or visitors or 1),
        series=[
            AnalyticsPoint(
                date=str(point.get("date") or ""),
                visitors=int(point.get("visitors") or 0),
                pageviews=int(point.get("pageviews") or 0),
                carts=int(point.get("carts") or 0),
                orders=int(point.get("orders") or 0),
            )
            for point in series_raw
        ],
        funnel=[
            AnalyticsFunnelStep(label="Visited home", value=home, pct=100 if home else 0),
            AnalyticsFunnelStep(label="Added to cart", value=carts, pct=_pct(carts, home or 1)),
            AnalyticsFunnelStep(label="Placed order", value=orders, pct=_pct(orders, home or 1)),
        ],
        top_pages=_counts(_as_rows(row["top_pages"])),
        top_countries=_country_counts(_as_rows(row["top_countries"])),
        devices=_counts(_as_rows(row["devices"])),
        top_events=_counts(_as_rows(row["top_events"])),
        top_referrers=_counts(_as_rows(row["top_referrers"])),
    )
