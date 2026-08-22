"""Admin dashboard — /admin/dashboard (aggregate reads only)."""

from datetime import date, datetime, timedelta
from json import loads
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.admin_order_status import admin_status_label
from app.core.deps import require_role
from app.core.report_fmt import delta_pct, inr, ist_now, start_of_day
from app.database import get_db
from app.dto.reports_dto import (
    AdminDashboardResponse,
    DashboardKpi,
    DayPoint,
    LowStockProp,
    RecentOrderRow,
    TopProductProp,
)

router = APIRouter(
    prefix="/admin/dashboard",
    tags=["admin-dashboard"],
    dependencies=[Depends(require_role("admin"))],
)

# One round-trip: remote Postgres RTT is ~90ms, so 9 sequential queries felt slow.
_DASHBOARD_SQL = text(
    """
    WITH order_stats AS (
        SELECT
            coalesce(sum(total) FILTER (
                WHERE created_at >= :period_start AND created_at < :period_end
            ), 0) AS rev_cur,
            count(*) FILTER (
                WHERE created_at >= :period_start AND created_at < :period_end
            ) AS ord_cur,
            coalesce(sum(total) FILTER (
                WHERE created_at >= :prev_start AND created_at < :period_start
            ), 0) AS rev_prev,
            count(*) FILTER (
                WHERE created_at >= :prev_start AND created_at < :period_start
            ) AS ord_prev
        FROM orders
        WHERE created_at >= :prev_start AND created_at < :period_end
    ),
    cust_stats AS (
        SELECT
            count(*) FILTER (
                WHERE created_at >= :period_start AND created_at < :period_end
            ) AS new_cur,
            count(*) FILTER (
                WHERE created_at >= :prev_start AND created_at < :period_start
            ) AS new_prev
        FROM customers
        WHERE created_at >= :prev_start AND created_at < :period_end
    ),
    trend AS (
        SELECT
            created_at::date AS d,
            coalesce(sum(total), 0) AS revenue,
            count(*) AS orders
        FROM orders
        WHERE created_at >= :period_start AND created_at < :period_end
        GROUP BY 1
    ),
    top AS (
        SELECT
            p.slug,
            p.name,
            b.name AS brand,
            (
                SELECT pi.url
                FROM product_images pi
                WHERE pi.product_id = p.id
                ORDER BY pi.sort_order ASC, pi.id ASC
                LIMIT 1
            ) AS image,
            p.price
        FROM (
            SELECT oi.product_id, sum(oi.qty) AS qty
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.created_at >= :period_start AND o.created_at < :period_end
            GROUP BY oi.product_id
            ORDER BY sum(oi.qty) DESC
            LIMIT 5
        ) sold
        JOIN products p ON p.id = sold.product_id
        LEFT JOIN brands b ON b.id = p.brand_id
        ORDER BY sold.qty DESC
    ),
    low AS (
        SELECT
            pv.sku,
            p.name,
            w.name AS warehouse,
            wi.on_hand AS stock,
            count(*) OVER () AS total
        FROM warehouse_inventory wi
        JOIN product_variants pv ON pv.id = wi.variant_id
        JOIN products p ON p.id = pv.product_id
        JOIN warehouses w ON w.id = wi.warehouse_id
        WHERE wi.on_hand <= wi.reorder_point
        ORDER BY wi.on_hand ASC
        LIMIT 12
    )
    SELECT json_build_object(
        'order_stats', (SELECT row_to_json(order_stats) FROM order_stats),
        'cust_stats', (SELECT row_to_json(cust_stats) FROM cust_stats),
        'trend', (SELECT coalesce(json_agg(trend ORDER BY d), '[]'::json) FROM trend),
        'recent', (
            SELECT coalesce(json_agg(r), '[]'::json)
            FROM (
                SELECT o.order_number, c.name AS customer, o.status, o.total
                FROM orders o
                JOIN customers c ON c.id = o.customer_id
                ORDER BY o.created_at DESC
                LIMIT 6
            ) r
        ),
        'top', (SELECT coalesce(json_agg(top), '[]'::json) FROM top),
        'low', (SELECT coalesce(json_agg(low ORDER BY stock), '[]'::json) FROM low)
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


@router.get("", response_model=AdminDashboardResponse)
def admin_dashboard(
    db: Session = Depends(get_db),
    days: int = Query(7, ge=7, le=30),
) -> AdminDashboardResponse:
    now = ist_now()
    today = start_of_day(now)
    period_start = today - timedelta(days=days - 1)
    period_end = today + timedelta(days=1)
    prev_start = period_start - timedelta(days=days)

    payload = db.execute(
        _DASHBOARD_SQL,
        {
            "period_start": period_start,
            "period_end": period_end,
            "prev_start": prev_start,
        },
    ).scalar() or {}
    if isinstance(payload, str):
        payload = loads(payload)

    order_stats = payload.get("order_stats") or {}
    cust_stats = payload.get("cust_stats") or {}
    rev_cur = float(order_stats.get("rev_cur") or 0)
    ord_cur = int(order_stats.get("ord_cur") or 0)
    rev_prev = float(order_stats.get("rev_prev") or 0)
    ord_prev = int(order_stats.get("ord_prev") or 0)
    new_cust = int(cust_stats.get("new_cur") or 0)
    new_cust_prev = int(cust_stats.get("new_prev") or 0)

    low_rows = payload.get("low") or []
    low_stock_count = int(low_rows[0].get("total") or 0) if low_rows else 0

    kpis = [
        DashboardKpi(
            label="Revenue (7d)",
            value=inr(rev_cur),
            delta=delta_pct(rev_cur, rev_prev),
        ),
        DashboardKpi(
            label="Orders (7d)",
            value=f"{ord_cur:,}",
            delta=delta_pct(float(ord_cur), float(ord_prev)),
        ),
        DashboardKpi(
            label="New customers",
            value=str(new_cust),
            delta=delta_pct(float(new_cust), float(new_cust_prev)),
        ),
        DashboardKpi(
            label="Low stock SKUs",
            value=str(low_stock_count),
            delta="Needs review" if low_stock_count else "Healthy",
        ),
    ]

    by_day: dict[date, tuple[float, int]] = {}
    for row in payload.get("trend") or []:
        d = _as_date(row.get("d"))
        if d is None:
            continue
        by_day[d] = (float(row.get("revenue") or 0), int(row.get("orders") or 0))
    sales_by_day: list[DayPoint] = []
    for i in range(days):
        d = (period_start + timedelta(days=i)).date()
        rev, cnt = by_day.get(d, (0.0, 0))
        sales_by_day.append(DayPoint(day=d.strftime("%a"), revenue=rev, orders=cnt))

    recent_orders = [
        RecentOrderRow(
            id=row.get("order_number") or "",
            customer=row.get("customer") or "Customer",
            status=admin_status_label(row.get("status") or ""),
            total=float(row.get("total") or 0),
        )
        for row in (payload.get("recent") or [])
    ]

    top_products = [
        TopProductProp(
            id=row.get("slug") or "",
            name=row.get("name") or "",
            brand=row.get("brand") or "",
            image=row.get("image") or "",
            price=float(row.get("price") or 0),
        )
        for row in (payload.get("top") or [])
    ]

    low_stock = [
        LowStockProp(
            sku=row.get("sku") or "",
            name=row.get("name") or "",
            warehouse=row.get("warehouse") or "",
            stock=int(row.get("stock") or 0),
        )
        for row in low_rows
    ]

    end_d = today.date()
    start_d = period_start.date()
    period_label = (
        f"Last {days} days · {start_d.strftime('%b %d')} – {end_d.strftime('%b %d, %Y')}"
    )

    return AdminDashboardResponse(
        periodLabel=period_label,
        kpis=kpis,
        salesByDay=sales_by_day,
        recentOrders=recent_orders,
        topProducts=top_products,
        lowStockAlerts=low_stock,
    )
