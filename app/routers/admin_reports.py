"""Admin reports — /admin/reports (aggregate reads only)."""

from datetime import date, datetime, timedelta
from json import loads
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.report_fmt import inr, ist_now, pct, start_of_day
from app.database import get_db
from app.dto.reports_dto import (
    AdminReportsResponse,
    CategorySlice,
    DayPoint,
    NamedKpi,
)

router = APIRouter(
    prefix="/admin/reports",
    tags=["admin-reports"],
    dependencies=[Depends(require_role("admin"))],
)

_REPORTS_SQL = text(
    """
    WITH trend AS (
        SELECT
            created_at::date AS d,
            coalesce(sum(total), 0) AS revenue,
            count(*) AS orders
        FROM orders
        WHERE created_at >= :since AND status <> 'cancelled'
        GROUP BY 1
    ),
    cat AS (
        SELECT
            coalesce(c.name, 'Other') AS name,
            coalesce(sum(coalesce(oi.price_snapshot, 0) * oi.qty), 0) AS value
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        JOIN products p ON p.id = oi.product_id
        LEFT JOIN categories c ON c.id = p.category_id
        WHERE o.created_at >= :since AND o.status <> 'cancelled'
        GROUP BY c.name
        ORDER BY value DESC
        LIMIT 8
    ),
    order_stats AS (
        SELECT
            count(*) AS total_orders,
            count(*) FILTER (WHERE status <> 'cancelled') AS paid_orders,
            coalesce(sum(total) FILTER (WHERE status <> 'cancelled'), 0) AS revenue,
            coalesce(avg(total) FILTER (WHERE status <> 'cancelled'), 0) AS aov,
            count(*) FILTER (WHERE status = 'cancelled') AS cancelled
        FROM orders
        WHERE created_at >= :since
    ),
    repeat_stats AS (
        SELECT
            count(*) AS cust_n,
            count(*) FILTER (WHERE cnt > 1) AS repeat_n
        FROM (
            SELECT customer_id, count(*) AS cnt
            FROM orders
            WHERE created_at >= :since AND status <> 'cancelled'
            GROUP BY customer_id
        ) cust_counts
    ),
    new_customers AS (
        SELECT count(*) AS n FROM customers WHERE created_at >= :since
    )
    SELECT json_build_object(
        'trend', (SELECT coalesce(json_agg(trend ORDER BY d), '[]'::json) FROM trend),
        'category', (SELECT coalesce(json_agg(cat ORDER BY value DESC), '[]'::json) FROM cat),
        'order_stats', (SELECT row_to_json(order_stats) FROM order_stats),
        'repeat_stats', (SELECT row_to_json(repeat_stats) FROM repeat_stats),
        'new_customers', (SELECT n FROM new_customers)
    )
    """
)


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return None


@router.get("", response_model=AdminReportsResponse)
def admin_reports(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=7, le=90),
) -> AdminReportsResponse:
    now = ist_now()
    since = start_of_day(now) - timedelta(days=days - 1)

    payload = db.execute(_REPORTS_SQL, {"since": since}).scalar() or {}
    if isinstance(payload, str):
        payload = loads(payload)

    by_day: dict[date, tuple[float, int]] = {}
    for row in payload.get("trend") or []:
        d = _as_date(row.get("d"))
        if d is None:
            continue
        by_day[d] = (float(row.get("revenue") or 0), int(row.get("orders") or 0))
    revenue_trend: list[DayPoint] = []
    day_fmt = "%a" if days <= 14 else "%m-%d"
    for i in range(days):
        d = (since + timedelta(days=i)).date()
        rev, cnt = by_day.get(d, (0.0, 0))
        revenue_trend.append(DayPoint(day=d.strftime(day_fmt), revenue=rev, orders=cnt))

    category_mix = [
        CategorySlice(
            name=(row.get("name") or "Other").lower(),
            value=round(float(row.get("value") or 0), 2),
        )
        for row in (payload.get("category") or [])
    ]

    order_stats = payload.get("order_stats") or {}
    repeat_stats = payload.get("repeat_stats") or {}
    total_orders = int(order_stats.get("total_orders") or 0)
    paid_orders = int(order_stats.get("paid_orders") or 0)
    revenue = float(order_stats.get("revenue") or 0)
    aov = float(order_stats.get("aov") or 0)
    cancelled = int(order_stats.get("cancelled") or 0)
    cancel_rate = (cancelled / total_orders * 100) if total_orders else 0.0

    cust_n = int(repeat_stats.get("cust_n") or 0)
    repeat_n = int(repeat_stats.get("repeat_n") or 0)
    repeat_rate = (repeat_n / cust_n * 100) if cust_n else 0.0

    new_customers = int(payload.get("new_customers") or 0)

    kpis = [
        NamedKpi(label="Revenue", value=inr(revenue)),
        NamedKpi(label="Orders", value=str(paid_orders)),
        NamedKpi(label="Avg order value", value=inr(aov)),
        NamedKpi(label="Repeat customer rate", value=pct(repeat_rate, 0)),
        NamedKpi(label="Cancellation rate", value=pct(cancel_rate)),
        NamedKpi(label="New customers", value=str(new_customers)),
    ]

    return AdminReportsResponse(
        revenueTrend=revenue_trend,
        categoryMix=category_mix,
        kpis=kpis,
    )
