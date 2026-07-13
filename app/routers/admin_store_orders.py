"""Admin store orders — /admin/store-orders."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, Date, func, select
from sqlalchemy.orm import Session

from app.core.store_orders import admin_order_row, list_store_orders_query
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.store_order_dto import (
    StoreAnalyticsKpis,
    StoreAnalyticsMixPoint,
    StoreAnalyticsResponse,
    StoreAnalyticsTrendPoint,
    StoreOrderListResponse,
    StoreOrderOut,
)
from app.schemas import Store, StoreOrder

router = APIRouter(prefix="/admin/store-orders", tags=["admin-store-orders"], dependencies=[Depends(require_role("admin"))])


@router.get("/analytics", response_model=StoreAnalyticsResponse)
def store_analytics(db: Session = Depends(get_db)) -> StoreAnalyticsResponse:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=13)

    # Today's KPIs from store_orders + open store staff counts
    today_rev = (
        db.scalar(
            select(func.coalesce(func.sum(StoreOrder.total), 0)).where(
                cast(StoreOrder.created_at, Date) == today,
                StoreOrder.status.in_(("Completed", "Collected")),
            )
        )
        or 0
    )
    today_orders = (
        db.scalar(
            select(func.count()).where(cast(StoreOrder.created_at, Date) == today)
        )
        or 0
    )
    staff = (
        db.scalar(
            select(func.coalesce(func.sum(Store.staff), 0)).where(Store.status == "Open")
        )
        or 0
    )
    rev_f = float(today_rev)
    ord_i = int(today_orders)
    staff_i = int(staff)
    kpis = StoreAnalyticsKpis(
        revenueToday=rev_f,
        ordersToday=ord_i,
        avgBasket=rev_f / max(1, ord_i),
        salesPerAssociate=rev_f / max(1, staff_i),
    )

    # 14-day trend GROUP BY date
    day_rows = db.execute(
        select(
            cast(StoreOrder.created_at, Date).label("d"),
            func.coalesce(func.sum(StoreOrder.total), 0),
            func.count(),
        )
        .where(cast(StoreOrder.created_at, Date) >= start)
        .group_by(cast(StoreOrder.created_at, Date))
        .order_by(cast(StoreOrder.created_at, Date))
    ).all()
    by_day = {r[0]: (float(r[1]), int(r[2])) for r in day_rows}
    trend = []
    for i in range(14):
        d = start + timedelta(days=i)
        revenue, orders = by_day.get(d, (0.0, 0))
        trend.append(
            StoreAnalyticsTrendPoint(
                day=f"D{i + 1}",
                revenue=revenue,
                orders=orders,
                footfall=orders * 5,
            )
        )

    # Revenue mix by store (completed/collected)
    mix_rows = db.execute(
        select(
            Store.name,
            func.coalesce(func.sum(StoreOrder.total), 0),
        )
        .join(StoreOrder, StoreOrder.store_id == Store.id)
        .where(StoreOrder.status.in_(("Completed", "Collected")))
        .group_by(Store.name)
        .order_by(func.sum(StoreOrder.total).desc())
    ).all()
    revenue_mix = []
    for name, rev in mix_rows:
        short = (name or "").split(" · ")[-1] if name else "Store"
        revenue_mix.append(StoreAnalyticsMixPoint(store=short, revenue=float(rev)))

    return StoreAnalyticsResponse(kpis=kpis, trend=trend, revenueMix=revenue_mix)


@router.get("", response_model=StoreOrderListResponse)
def list_store_orders(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    store: str | None = None,
    search: str | None = Query(None, alias="q"),
) -> StoreOrderListResponse:
    limit, offset = page
    stmt, count_stmt = list_store_orders_query(
        status=status_filter,
        store_name=store,
        search=search,
    )
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(StoreOrder.id.desc()).limit(limit).offset(offset)
    ).all()

    status_counts = dict(
        db.execute(
            select(StoreOrder.status, func.count()).group_by(StoreOrder.status)
        ).all()
    )
    counts = {"All": sum(int(v) for v in status_counts.values())}
    for s, n in status_counts.items():
        counts[s] = int(n)

    return StoreOrderListResponse(
        items=[StoreOrderOut(**admin_order_row(o)) for o in rows],
        total=total,
        limit=limit,
        offset=offset,
        counts=counts,
    )
