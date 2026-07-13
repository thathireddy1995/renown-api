"""Admin dashboard — /admin/dashboard (aggregate reads only)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import cast, Date, func, select
from sqlalchemy.orm import Session

from app.core.admin_order_status import admin_status_label
from app.core.deps import require_role
from app.core.report_fmt import delta_pct, inr, start_of_day, utcnow
from app.database import get_db
from app.dto.reports_dto import (
    AdminDashboardResponse,
    DashboardKpi,
    DayPoint,
    LowStockProp,
    RecentOrderRow,
    TopProductProp,
)
from app.schemas import (
    Brand,
    Customer,
    Order,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
    Warehouse,
    WarehouseInventory,
)

router = APIRouter(
    prefix="/admin/dashboard",
    tags=["admin-dashboard"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("", response_model=AdminDashboardResponse)
def admin_dashboard(
    db: Session = Depends(get_db),
    days: int = Query(7, ge=7, le=30),
) -> AdminDashboardResponse:
    now = utcnow()
    today = start_of_day(now)
    period_start = today - timedelta(days=days - 1)
    prev_start = period_start - timedelta(days=days)
    prev_end = period_start

    def _period_stats(start, end):
        return db.execute(
            select(
                func.coalesce(func.sum(Order.total), 0),
                func.count(Order.id),
            ).where(Order.created_at >= start, Order.created_at < end)
        ).one()

    cur = _period_stats(period_start, today + timedelta(days=1))
    prev = _period_stats(prev_start, prev_end)
    rev_cur, ord_cur = float(cur[0] or 0), int(cur[1] or 0)
    rev_prev, ord_prev = float(prev[0] or 0), int(prev[1] or 0)

    new_cust = db.scalar(
        select(func.count()).where(
            Customer.created_at >= period_start,
            Customer.created_at < today + timedelta(days=1),
        )
    ) or 0
    new_cust_prev = db.scalar(
        select(func.count()).where(
            Customer.created_at >= prev_start,
            Customer.created_at < prev_end,
        )
    ) or 0

    # Low stock in one query
    low_stock_count = db.scalar(
        select(func.count()).select_from(WarehouseInventory).where(
            WarehouseInventory.on_hand <= WarehouseInventory.reorder_point
        )
    ) or 0

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

    day_col = cast(Order.created_at, Date).label("d")
    trend_rows = db.execute(
        select(
            day_col,
            func.coalesce(func.sum(Order.total), 0),
            func.count(Order.id),
        )
        .where(Order.created_at >= period_start)
        .group_by(day_col)
        .order_by(day_col.asc())
    ).all()
    by_day = {
        r[0]: (float(r[1] or 0), int(r[2] or 0)) for r in trend_rows if r[0] is not None
    }
    sales_by_day: list[DayPoint] = []
    for i in range(days):
        d = (period_start + timedelta(days=i)).date()
        rev, cnt = by_day.get(d, (0.0, 0))
        sales_by_day.append(DayPoint(day=d.strftime("%a"), revenue=rev, orders=cnt))

    # Recent orders — single query with customer join
    recent_rows = db.execute(
        select(
            Order.order_number,
            Customer.name,
            Order.status,
            Order.total,
        )
        .join(Customer, Customer.id == Order.customer_id)
        .order_by(Order.created_at.desc())
        .limit(6)
    ).all()
    recent_orders = [
        RecentOrderProp(
            id=r[0],
            customer=r[1] or "Customer",
            status=admin_status_label(r[2] or ""),
            total=float(r[3] or 0),
        )
        for r in recent_rows
    ]

    # Top products by qty sold — single aggregate + image via lateral/min id
    top_sub = (
        select(
            OrderItem.product_id.label("pid"),
            func.sum(OrderItem.qty).label("qty"),
            func.coalesce(
                func.sum(func.coalesce(OrderItem.price_snapshot, 0) * OrderItem.qty), 0
            ).label("rev"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.created_at >= period_start)
        .group_by(OrderItem.product_id)
        .order_by(func.sum(OrderItem.qty).desc())
        .limit(5)
        .subquery()
    )
    img_sub = (
        select(
            ProductImage.product_id.label("pid"),
            func.min(ProductImage.url).label("url"),
        )
        .group_by(ProductImage.product_id)
        .subquery()
    )
    top_rows = db.execute(
        select(
            Product.slug,
            Product.name,
            Brand.name,
            img_sub.c.url,
            Product.price,
        )
        .select_from(top_sub)
        .join(Product, Product.id == top_sub.c.pid)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(img_sub, img_sub.c.pid == Product.id)
        .order_by(top_sub.c.qty.desc())
    ).all()
    top_products = [
        TopProductProp(
            id=r[0] or "",
            name=r[1] or "",
            brand=r[2] or "",
            image=r[3] or "",
            price=float(r[4] or 0),
        )
        for r in top_rows
    ]

    low_rows = db.execute(
        select(
            ProductVariant.sku,
            Product.name,
            Warehouse.name,
            WarehouseInventory.on_hand,
        )
        .join(ProductVariant, ProductVariant.id == WarehouseInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Warehouse, Warehouse.id == WarehouseInventory.warehouse_id)
        .where(WarehouseInventory.on_hand <= WarehouseInventory.reorder_point)
        .order_by(WarehouseInventory.on_hand.asc())
        .limit(12)
    ).all()
    low_stock = [
        LowStockProp(
            sku=r[0] or "",
            name=r[1] or "",
            warehouse=r[2] or "",
            stock=int(r[3] or 0),
        )
        for r in low_rows
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
