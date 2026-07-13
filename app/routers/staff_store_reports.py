"""Staff store reports + dashboard — aggregate reads scoped by JWT store_id."""

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import cast, Date, func, select
from sqlalchemy.orm import Session

from app.core.clinical import TYPE_LABEL, default_store
from app.core.deps import TokenPrincipal, require_role
from app.core.report_fmt import (
    delta_count,
    delta_pct,
    inr,
    inr_lakhs,
    month_label,
    pct,
    start_of_day,
    utcnow,
)
from app.core.store_orders import staff_order_row
from app.database import get_db
from app.dto.reports_dto import (
    CategoryUnits,
    DashboardKpi,
    MonthPoint,
    StaffSalesPoint,
    StaffStoreDashboardResponse,
    StaffStoreReportsResponse,
    StoreAppointment,
    StoreRecentOrder,
    WeekPoint,
)
from app.schemas import (
    Appointment,
    Category,
    Customer,
    Doctor,
    Product,
    ProductVariant,
    StoreOrder,
    StoreOrderItem,
)

reports_router = APIRouter(
    prefix="/staff/store/reports",
    tags=["staff-store-reports"],
    dependencies=[Depends(require_role("store_manager"))],
)

dashboard_router = APIRouter(
    prefix="/staff/store/dashboard",
    tags=["staff-store-dashboard"],
    dependencies=[Depends(require_role("store_manager"))],
)


def _store_id(db: Session, principal: TokenPrincipal) -> int | None:
    if principal.store_id is not None:
        return principal.store_id
    store = default_store(db)
    return store.id if store else None


@reports_router.get("", response_model=StaffStoreReportsResponse)
def store_reports(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffStoreReportsResponse:
    sid = _store_id(db, principal)
    now = utcnow()
    today = start_of_day(now)
    month_start = today.replace(day=1)
    prev_month_end = month_start
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

    def _mtd(start, end):
        if sid is None:
            return 0.0, 0, 0.0
        row = db.execute(
            select(
                func.coalesce(func.sum(StoreOrder.total), 0),
                func.count(StoreOrder.id),
                func.coalesce(func.avg(StoreOrder.total), 0),
            ).where(
                StoreOrder.store_id == sid,
                StoreOrder.created_at >= start,
                StoreOrder.created_at < end,
            )
        ).one()
        return float(row[0] or 0), int(row[1] or 0), float(row[2] or 0)

    rev, orders, avg_bill = _mtd(month_start, today + timedelta(days=1))
    prev_rev, prev_orders, prev_avg = _mtd(prev_month_start, prev_month_end)

    # Conversion proxy: completed / all store orders this month
    completed = 0
    if sid is not None:
        completed = db.scalar(
            select(func.count()).where(
                StoreOrder.store_id == sid,
                StoreOrder.created_at >= month_start,
                StoreOrder.status.in_(["Completed", "Collected", "Ready"]),
            )
        ) or 0
    conversion = (completed / orders * 100) if orders else 0.0
    prev_completed = 0
    if sid is not None:
        prev_completed = db.scalar(
            select(func.count()).where(
                StoreOrder.store_id == sid,
                StoreOrder.created_at >= prev_month_start,
                StoreOrder.created_at < prev_month_end,
                StoreOrder.status.in_(["Completed", "Collected", "Ready"]),
            )
        ) or 0
    prev_conversion = (prev_completed / prev_orders * 100) if prev_orders else 0.0

    kpis = [
        DashboardKpi(
            label="MTD Revenue",
            value=inr_lakhs(rev),
            delta=delta_pct(rev, prev_rev),
        ),
        DashboardKpi(
            label="Orders",
            value=f"{orders:,}",
            delta=delta_count(orders, prev_orders),
        ),
        DashboardKpi(
            label="Avg. bill value",
            value=inr(avg_bill),
            delta=delta_count(int(avg_bill), int(prev_avg), suffix=""),
        ),
        DashboardKpi(
            label="Conversion",
            value=pct(conversion),
            delta=delta_pct(conversion, prev_conversion),
        ),
    ]

    # Monthly revenue trend (last 6 months) in lakhs — one GROUP BY
    six_ago = (month_start - timedelta(days=160)).replace(day=1)
    month_expr = func.date_trunc("month", StoreOrder.created_at)
    trend_q = select(
        month_expr.label("m"),
        func.coalesce(func.sum(StoreOrder.total), 0),
    ).where(StoreOrder.created_at >= six_ago)
    if sid is not None:
        trend_q = trend_q.where(StoreOrder.store_id == sid)
    trend_rows = db.execute(
        trend_q.group_by(month_expr).order_by(month_expr.asc())
    ).all()
    by_month = {}
    for r in trend_rows:
        if r[0] is None:
            continue
        d = r[0].date() if hasattr(r[0], "date") else r[0]
        by_month[d.replace(day=1) if hasattr(d, "replace") else d] = float(r[1] or 0)

    revenue_trend: list[MonthPoint] = []
    cursor = six_ago
    for _ in range(6):
        key = cursor.date().replace(day=1)
        revenue_trend.append(
            MonthPoint(m=month_label(key), v=round(by_month.get(key, 0.0) / 100_000.0, 1))
        )
        # next month
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)

    # Top staff by sales — associate_name GROUP BY
    staff_q = (
        select(
            StoreOrder.associate_name,
            func.coalesce(func.sum(StoreOrder.total), 0),
        )
        .where(
            StoreOrder.created_at >= month_start,
            StoreOrder.associate_name.is_not(None),
            StoreOrder.associate_name != "",
        )
        .group_by(StoreOrder.associate_name)
        .order_by(func.sum(StoreOrder.total).desc())
        .limit(6)
    )
    if sid is not None:
        staff_q = staff_q.where(StoreOrder.store_id == sid)
    staff_rows = db.execute(staff_q).all()
    top_staff = [
        StaffSalesPoint(
            name=(r[0] or "—").split(" ")[0],
            sales=round(float(r[1] or 0) / 1000, 0),
        )
        for r in staff_rows
    ]

    return StaffStoreReportsResponse(
        kpis=kpis, revenueTrend=revenue_trend, topStaff=top_staff
    )


@dashboard_router.get("", response_model=StaffStoreDashboardResponse)
def store_dashboard(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffStoreDashboardResponse:
    sid = _store_id(db, principal)
    now = utcnow()
    today = start_of_day(now)
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=6)

    def _day_stats(start, end):
        if sid is None:
            return 0.0, 0, 0
        row = db.execute(
            select(
                func.coalesce(func.sum(StoreOrder.total), 0),
                func.count(StoreOrder.id),
                func.coalesce(func.sum(StoreOrderItem.qty), 0),
            )
            .select_from(StoreOrder)
            .outerjoin(StoreOrderItem, StoreOrderItem.store_order_id == StoreOrder.id)
            .where(
                StoreOrder.store_id == sid,
                StoreOrder.created_at >= start,
                StoreOrder.created_at < end,
            )
        ).one()
        return float(row[0] or 0), int(row[1] or 0), int(row[2] or 0)

    rev_t, ord_t, frames_t = _day_stats(today, today + timedelta(days=1))
    rev_y, ord_y, frames_y = _day_stats(yesterday, today)

    # Walk-ins: in_store channel count today
    walk_t = walk_y = 0
    if sid is not None:
        walk_t = db.scalar(
            select(func.count()).where(
                StoreOrder.store_id == sid,
                StoreOrder.channel == "in_store",
                StoreOrder.created_at >= today,
            )
        ) or 0
        walk_y = db.scalar(
            select(func.count()).where(
                StoreOrder.store_id == sid,
                StoreOrder.channel == "in_store",
                StoreOrder.created_at >= yesterday,
                StoreOrder.created_at < today,
            )
        ) or 0

    frames_trend = "down" if frames_t < frames_y else "up"
    kpis = [
        DashboardKpi(
            label="Today's revenue",
            value=inr(rev_t),
            delta=f"{delta_pct(rev_t, rev_y)} vs yesterday",
        ),
        DashboardKpi(
            label="Orders",
            value=str(ord_t),
            delta=f"{delta_count(ord_t, ord_y)} vs yesterday",
        ),
        DashboardKpi(
            label="Walk-ins",
            value=str(walk_t),
            delta=f"{delta_count(walk_t, walk_y)} vs yesterday",
        ),
        DashboardKpi(
            label="Frames sold",
            value=str(frames_t),
            delta=f"{delta_count(frames_t, frames_y)} vs yesterday",
        ),
    ]

    day_col = cast(StoreOrder.created_at, Date)
    week_q = select(
        day_col.label("d"),
        func.coalesce(func.sum(StoreOrder.total), 0),
    ).where(StoreOrder.created_at >= week_start)
    if sid is not None:
        week_q = week_q.where(StoreOrder.store_id == sid)
    week_rows = db.execute(week_q.group_by(day_col).order_by(day_col.asc())).all()
    by_d = {r[0]: float(r[1] or 0) for r in week_rows if r[0]}
    weekly: list[WeekPoint] = []
    for i in range(7):
        d = (week_start + timedelta(days=i)).date()
        weekly.append(WeekPoint(d=d.strftime("%a"), v=by_d.get(d, 0.0)))

    week_total = sum(p.v for p in weekly)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_rev = 0.0
    if sid is not None:
        prev_week_rev = float(
            db.scalar(
                select(func.coalesce(func.sum(StoreOrder.total), 0)).where(
                    StoreOrder.store_id == sid,
                    StoreOrder.created_at >= prev_week_start,
                    StoreOrder.created_at < week_start,
                )
            )
            or 0
        )
    weekly_delta = delta_pct(week_total, prev_week_rev)

    cat_q = (
        select(
            func.coalesce(Category.name, "Other"),
            func.coalesce(func.sum(StoreOrderItem.qty), 0),
        )
        .select_from(StoreOrderItem)
        .join(StoreOrder, StoreOrder.id == StoreOrderItem.store_order_id)
        .join(ProductVariant, ProductVariant.id == StoreOrderItem.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(StoreOrder.created_at >= week_start)
        .group_by(Category.name)
        .order_by(func.sum(StoreOrderItem.qty).desc())
        .limit(6)
    )
    if sid is not None:
        cat_q = cat_q.where(StoreOrder.store_id == sid)
    cat_rows = db.execute(cat_q).all()
    sales_by_category = [
        CategoryUnits(name=r[0] or "Other", v=float(r[1] or 0)) for r in cat_rows
    ]

    recent_q = (
        select(StoreOrder)
        .order_by(StoreOrder.created_at.desc())
        .limit(5)
    )
    if sid is not None:
        recent_q = recent_q.where(StoreOrder.store_id == sid)
    recent = db.scalars(recent_q).all()
    # items summary in one query
    order_ids = [o.id for o in recent]
    items_map: dict[int, str] = {}
    if order_ids:
        item_rows = db.execute(
            select(
                StoreOrderItem.store_order_id,
                func.string_agg(Product.name, ", "),
            )
            .join(ProductVariant, ProductVariant.id == StoreOrderItem.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(StoreOrderItem.store_order_id.in_(order_ids))
            .group_by(StoreOrderItem.store_order_id)
        ).all()
        items_map = {int(r[0]): (r[1] or "—") for r in item_rows}

    recent_orders = []
    for o in recent:
        row = staff_order_row(o)
        recent_orders.append(
            StoreRecentOrder(
                id=row["id"],
                customer=row["customer"],
                items=items_map.get(o.id, "—"),
                total=row["total"],
                status=row["status"],
            )
        )

    appt_q = (
        select(
            Appointment.scheduled_at,
            Customer.name,
            Appointment.appointment_type,
            Doctor.name,
            Appointment.phone,
        )
        .outerjoin(Customer, Customer.id == Appointment.customer_id)
        .outerjoin(Doctor, Doctor.id == Appointment.doctor_id)
        .where(
            Appointment.scheduled_at >= today,
            Appointment.scheduled_at < today + timedelta(days=1),
            Appointment.status != "cancelled",
        )
        .order_by(Appointment.scheduled_at.asc())
        .limit(8)
    )
    if sid is not None:
        appt_q = appt_q.where(Appointment.store_id == sid)
    appt_rows = db.execute(appt_q).all()
    appointments = []
    for r in appt_rows:
        t = r[0]
        appointments.append(
            StoreAppointment(
                time=t.strftime("%H:%M") if t else "—",
                name=r[1] or r[4] or "Walk-in",
                type=TYPE_LABEL.get(r[2] or "", r[2] or "Eye Test"),
                doctor=r[3] or "—",
            )
        )

    return StaffStoreDashboardResponse(
        kpis=kpis,
        weeklySales=weekly,
        salesByCategory=sales_by_category,
        recentOrders=recent_orders,
        appointments=appointments,
        weeklyDelta=weekly_delta,
        framesSoldTrend=frames_trend,
    )
