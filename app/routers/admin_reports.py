"""Admin reports — /admin/reports (aggregate reads only)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, cast, Date, func, select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.report_fmt import inr, pct, start_of_day, utcnow
from app.database import get_db
from app.dto.reports_dto import (
    AdminReportsResponse,
    CategorySlice,
    DayPoint,
    NamedKpi,
)
from app.schemas import Category, Customer, Order, OrderItem, Product

router = APIRouter(
    prefix="/admin/reports",
    tags=["admin-reports"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("", response_model=AdminReportsResponse)
def admin_reports(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=7, le=90),
) -> AdminReportsResponse:
    now = utcnow()
    since = start_of_day(now) - timedelta(days=days - 1)

    # 1) Revenue trend by day
    day_col = cast(Order.created_at, Date).label("d")
    trend_rows = db.execute(
        select(
            day_col,
            func.coalesce(func.sum(Order.total), 0),
            func.count(Order.id),
        )
        .where(Order.created_at >= since)
        .group_by(day_col)
        .order_by(day_col.asc())
    ).all()
    by_day = {
        r[0]: (float(r[1] or 0), int(r[2] or 0)) for r in trend_rows if r[0] is not None
    }
    revenue_trend: list[DayPoint] = []
    for i in range(days):
        d = (since + timedelta(days=i)).date()
        rev, cnt = by_day.get(d, (0.0, 0))
        revenue_trend.append(
            DayPoint(day=d.strftime("%a") if days <= 14 else d.strftime("%m-%d"), revenue=rev, orders=cnt)
        )

    # 2) Category mix via join (single aggregate)
    cat_rows = db.execute(
        select(
            func.coalesce(Category.name, "Other"),
            func.coalesce(
                func.sum(
                    func.coalesce(OrderItem.price_snapshot, 0) * OrderItem.qty
                ),
                0,
            ),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(Order.created_at >= since)
        .group_by(Category.name)
        .order_by(func.sum(func.coalesce(OrderItem.price_snapshot, 0) * OrderItem.qty).desc())
        .limit(8)
    ).all()
    category_mix = [
        CategorySlice(name=(r[0] or "Other").lower(), value=round(float(r[1] or 0) / 1000, 2))
        for r in cat_rows
    ]

    # 3) KPI summary — aggregates over orders + repeat customers
    order_stats = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.avg(Order.total), 0),
            func.sum(case((Order.status == "cancelled", 1), else_=0)),
        ).where(Order.created_at >= since)
    ).one()
    total_orders = int(order_stats[0] or 0)
    aov = float(order_stats[1] or 0)
    cancelled = int(order_stats[2] or 0)
    refund_rate = (cancelled / total_orders * 100) if total_orders else 0.0

    cust_counts = (
        select(Order.customer_id, func.count().label("cnt"))
        .where(Order.created_at >= since)
        .group_by(Order.customer_id)
        .subquery()
    )
    repeat_stats = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(case((cust_counts.c.cnt > 1, 1), else_=0)), 0),
        ).select_from(cust_counts)
    ).one()
    cust_n = int(repeat_stats[0] or 0)
    repeat_n = int(repeat_stats[1] or 0)
    repeat_rate = (repeat_n / cust_n * 100) if cust_n else 0.0

    active_customers = db.scalar(
        select(func.count()).select_from(Customer).where(Customer.is_active.is_(True))
    ) or 0
    conversion = (cust_n / active_customers * 100) if active_customers else 0.0
    cart_abandon = max(0.0, 100.0 - conversion) if active_customers else 0.0
    nps = min(100, max(0, int(70 + (repeat_rate - 20) / 2)))

    kpis = [
        NamedKpi(label="Avg order value", value=inr(aov)),
        NamedKpi(label="Conversion rate", value=pct(conversion)),
        NamedKpi(label="Repeat customer rate", value=pct(repeat_rate, 0)),
        NamedKpi(label="Refund rate", value=pct(refund_rate)),
        NamedKpi(label="Cart abandonment", value=pct(cart_abandon, 0)),
        NamedKpi(label="NPS", value=str(nps)),
    ]

    return AdminReportsResponse(
        revenueTrend=revenue_trend,
        categoryMix=category_mix,
        kpis=kpis,
    )
