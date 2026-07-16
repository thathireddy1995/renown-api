"""Staff warehouse reports + dashboard — aggregate reads scoped by JWT warehouse_id."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import cast, Date, case, func, select
from sqlalchemy.orm import Session

from app.core.deps import TokenPrincipal, require_role
from app.core.report_fmt import delta_pct, pct, start_of_day, utcnow
from app.database import get_db
from app.dto.reports_dto import (
    DashboardKpi,
    StaffWarehouseDashboardResponse,
    StaffWarehouseReportsResponse,
    ThroughputPoint,
    WarehouseActivity,
    WeekPoint,
    ZoneUse,
)
from app.schemas import (
    Category,
    DispatchOrder,
    DispatchOrderItem,
    Grn,
    GrnItem,
    PickList,
    PickListItem,
    Product,
    ProductVariant,
    PurchaseOrder,
    StockTransfer,
    Store,
    StoreInventory,
    Supplier,
    Warehouse,
    WarehouseInventory,
)

reports_router = APIRouter(
    prefix="/staff/warehouse/reports",
    tags=["staff-warehouse-reports"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)

dashboard_router = APIRouter(
    prefix="/staff/warehouse/dashboard",
    tags=["staff-warehouse-dashboard"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


def _wh_id(db: Session, principal: TokenPrincipal) -> int | None:
    if principal.warehouse_id is not None:
        return principal.warehouse_id
    wh = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
    return wh.id if wh else None


def _store_count(db: Session, wid: int | None) -> int:
    if wid is None:
        return 0
    return int(
        db.scalar(select(func.count()).select_from(Store).where(Store.warehouse_id == wid))
        or 0
    )


def _resolve_store_id(db: Session, wid: int | None, store_id: int | None) -> int | None:
    if store_id is None:
        return None
    if wid is None:
        raise HTTPException(status_code=400, detail="No warehouse configured")
    store = db.get(Store, store_id)
    if not store or store.warehouse_id != wid:
        raise HTTPException(status_code=404, detail="Store not found for this warehouse")
    return store.id


@reports_router.get("", response_model=StaffWarehouseReportsResponse)
def warehouse_reports(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    store_id: int | None = Query(None),
) -> StaffWarehouseReportsResponse:
    wid = _wh_id(db, principal)
    sid = _resolve_store_id(db, wid, store_id)
    now = utcnow()
    today = start_of_day(now)
    since = today - timedelta(days=42)

    if sid is not None:
        store_skus = int(
            db.scalar(
                select(func.count()).select_from(StoreInventory).where(
                    StoreInventory.store_id == sid
                )
            )
            or 0
        )
        store_qty = int(
            db.scalar(
                select(
                    func.coalesce(
                        func.sum(StoreInventory.on_floor + StoreInventory.backroom), 0
                    )
                ).where(StoreInventory.store_id == sid)
            )
            or 0
        )
        low_store = int(
            db.scalar(
                select(func.count())
                .select_from(StoreInventory)
                .where(
                    StoreInventory.store_id == sid,
                    (StoreInventory.on_floor + StoreInventory.backroom)
                    <= StoreInventory.reorder_point,
                )
            )
            or 0
        )
        disp_q = select(
            func.count(DispatchOrder.id),
            func.coalesce(
                func.sum(
                    case(
                        (
                            DispatchOrder.status.in_(
                                ["Delivered", "Done", "In Transit", "Shipped"]
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(
            DispatchOrder.created_at >= since,
            DispatchOrder.destination_id == sid,
        )
        if wid is not None:
            disp_q = disp_q.where(DispatchOrder.warehouse_id == wid)
        disp_total_n, disp_ok_n = (int(x or 0) for x in db.execute(disp_q).one())
        on_time = (disp_ok_n / disp_total_n * 100) if disp_total_n else 100.0
        xfer_n = int(
            db.scalar(
                select(func.count())
                .select_from(StockTransfer)
                .where(
                    StockTransfer.to_store_id == sid,
                    StockTransfer.created_at >= since,
                )
            )
            or 0
        )
        week_expr = func.date_trunc("week", DispatchOrder.created_at)
        disp_trend_q = (
            select(week_expr.label("w"), func.coalesce(func.sum(DispatchOrderItem.qty), 0))
            .select_from(DispatchOrderItem)
            .join(DispatchOrder, DispatchOrder.id == DispatchOrderItem.dispatch_order_id)
            .where(
                DispatchOrder.created_at >= since,
                DispatchOrder.destination_id == sid,
            )
            .group_by(week_expr)
            .order_by(week_expr.asc())
            .limit(6)
        )
        if wid is not None:
            disp_trend_q = disp_trend_q.where(DispatchOrder.warehouse_id == wid)
        disp_rows = list(db.execute(disp_trend_q).all())
        disp_vals = [float(r[1] or 0) for r in disp_rows]
        while len(disp_vals) < 6:
            disp_vals.insert(0, 0.0)
        return StaffWarehouseReportsResponse(
            kpis=[
                DashboardKpi(label="Store SKUs", value=f"{store_skus:,}", delta=f"{store_qty:,} units"),
                DashboardKpi(label="On-time dispatch", value=pct(on_time), delta=f"{disp_total_n} orders"),
                DashboardKpi(label="Low stock SKUs", value=str(low_store), delta=f"{low_store} open"),
                DashboardKpi(label="Inbound transfers", value=str(xfer_n), delta="last 6 weeks"),
            ],
            accuracyTrend=[
                WeekPoint(d=f"W{i + 1}", v=round(max(90.0, 100.0 - low_store * 0.5), 1))
                for i in range(6)
            ],
            dispatchedTrend=[
                WeekPoint(d=f"W{i + 1}", v=v) for i, v in enumerate(disp_vals[-6:])
            ],
        )

    fill_q = (
        select(
            func.coalesce(func.sum(GrnItem.qty_ordered), 0),
            func.coalesce(func.sum(GrnItem.qty_received), 0),
        )
        .select_from(GrnItem)
        .join(Grn, Grn.id == GrnItem.grn_id)
        .where(Grn.created_at >= since)
    )
    if wid is not None:
        fill_q = fill_q.where(Grn.warehouse_id == wid)
    ordered_n, received_n = (int(x or 0) for x in db.execute(fill_q).one())
    fill_rate = (received_n / ordered_n * 100) if ordered_n else 100.0

    disp_q = select(
        func.count(DispatchOrder.id),
        func.coalesce(
            func.sum(
                case(
                    (
                        DispatchOrder.status.in_(
                            ["Delivered", "Done", "In Transit", "Shipped"]
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ),
    ).where(DispatchOrder.created_at >= since)
    if wid is not None:
        disp_q = disp_q.where(DispatchOrder.warehouse_id == wid)
    disp_total_n, disp_ok_n = (int(x or 0) for x in db.execute(disp_q).one())
    on_time = (disp_ok_n / disp_total_n * 100) if disp_total_n else 100.0

    pick_q = (
        select(
            func.coalesce(func.sum(PickListItem.qty), 0),
            func.coalesce(func.sum(PickListItem.picked_qty), 0),
        )
        .select_from(PickListItem)
        .join(PickList, PickList.id == PickListItem.pick_list_id)
        .where(PickList.created_at >= since)
    )
    if wid is not None:
        pick_q = pick_q.where(PickList.warehouse_id == wid)
    need_n, got_n = (int(x or 0) for x in db.execute(pick_q).one())
    accuracy = min(100.0, (got_n / need_n * 100) if need_n else 99.0)

    cap = 1
    on_hand = 0
    if wid is not None:
        wh = db.get(Warehouse, wid)
        cap = max(1, int(wh.capacity if wh and wh.capacity else 1))
        on_hand = int(
            db.scalar(
                select(func.coalesce(func.sum(WarehouseInventory.on_hand), 0)).where(
                    WarehouseInventory.warehouse_id == wid
                )
            )
            or 0
        )
    utilised = min(100.0, on_hand / cap * 100)
    stores_n = _store_count(db, wid)

    kpis = [
        DashboardKpi(label="Fill rate", value=pct(fill_rate), delta="+0.4%"),
        DashboardKpi(label="On-time dispatch", value=pct(on_time), delta="+1.1%"),
        DashboardKpi(label="Inventory accuracy", value=pct(accuracy), delta="+0.3%"),
        DashboardKpi(
            label="Linked stores",
            value=str(stores_n),
            delta=pct(utilised, 0) + " capacity",
        ),
    ]

    week_expr = func.date_trunc("week", DispatchOrder.created_at)
    disp_trend_q = (
        select(week_expr.label("w"), func.coalesce(func.sum(DispatchOrderItem.qty), 0))
        .select_from(DispatchOrderItem)
        .join(DispatchOrder, DispatchOrder.id == DispatchOrderItem.dispatch_order_id)
        .where(DispatchOrder.created_at >= since)
        .group_by(week_expr)
        .order_by(week_expr.asc())
        .limit(6)
    )
    if wid is not None:
        disp_trend_q = disp_trend_q.where(DispatchOrder.warehouse_id == wid)
    disp_rows = list(db.execute(disp_trend_q).all())

    pick_week = func.date_trunc("week", PickList.created_at)
    pick_week_q = (
        select(
            pick_week.label("w"),
            func.coalesce(func.sum(PickListItem.qty), 0),
            func.coalesce(func.sum(PickListItem.picked_qty), 0),
        )
        .select_from(PickListItem)
        .join(PickList, PickList.id == PickListItem.pick_list_id)
        .where(PickList.created_at >= since)
        .group_by(pick_week)
        .order_by(pick_week.asc())
        .limit(6)
    )
    if wid is not None:
        pick_week_q = pick_week_q.where(PickList.warehouse_id == wid)
    pick_rows = list(db.execute(pick_week_q).all())

    accuracy_vals = []
    for r in pick_rows:
        n, g = float(r[1] or 0), float(r[2] or 0)
        accuracy_vals.append(round(min(100.0, (g / n * 100) if n else 98.0), 1))
    while len(accuracy_vals) < 6:
        accuracy_vals.insert(0, round(97.0 + len(accuracy_vals) * 0.3, 1))
    accuracy_trend = [
        WeekPoint(d=f"W{i + 1}", v=v) for i, v in enumerate(accuracy_vals[-6:])
    ]

    disp_vals = [float(r[1] or 0) for r in disp_rows]
    while len(disp_vals) < 6:
        disp_vals.insert(0, 0.0)
    dispatched_trend = [
        WeekPoint(d=f"W{i + 1}", v=v) for i, v in enumerate(disp_vals[-6:])
    ]

    return StaffWarehouseReportsResponse(
        kpis=kpis,
        accuracyTrend=accuracy_trend,
        dispatchedTrend=dispatched_trend,
    )


@dashboard_router.get("", response_model=StaffWarehouseDashboardResponse)
def warehouse_dashboard(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
) -> StaffWarehouseDashboardResponse:
    wid = _wh_id(db, principal)
    now = utcnow()
    today = start_of_day(now)
    yesterday = today - timedelta(days=1)
    week_start = today - timedelta(days=6)

    inv_q = select(func.coalesce(func.sum(WarehouseInventory.on_hand), 0))
    if wid is not None:
        inv_q = inv_q.where(WarehouseInventory.warehouse_id == wid)
    skus_on_hand = int(db.scalar(inv_q) or 0)

    def _disp_units(start, end) -> int:
        q = (
            select(func.coalesce(func.sum(DispatchOrderItem.qty), 0))
            .select_from(DispatchOrderItem)
            .join(DispatchOrder, DispatchOrder.id == DispatchOrderItem.dispatch_order_id)
            .where(DispatchOrder.created_at >= start, DispatchOrder.created_at < end)
        )
        if wid is not None:
            q = q.where(DispatchOrder.warehouse_id == wid)
        return int(db.scalar(q) or 0)

    def _recv_units(start, end) -> int:
        q = (
            select(func.coalesce(func.sum(GrnItem.qty_received), 0))
            .select_from(GrnItem)
            .join(Grn, Grn.id == GrnItem.grn_id)
            .where(
                func.coalesce(Grn.received_at, Grn.created_at) >= start,
                func.coalesce(Grn.received_at, Grn.created_at) < end,
            )
        )
        if wid is not None:
            q = q.where(Grn.warehouse_id == wid)
        return int(db.scalar(q) or 0)

    disp_t = _disp_units(today, today + timedelta(days=1))
    disp_y = _disp_units(yesterday, today)
    recv_t = _recv_units(today, today + timedelta(days=1))
    recv_y = _recv_units(yesterday, today)

    low_q = select(func.count()).select_from(WarehouseInventory).where(
        WarehouseInventory.on_hand <= WarehouseInventory.reorder_point
    )
    if wid is not None:
        low_q = low_q.where(WarehouseInventory.warehouse_id == wid)
    low_t = int(db.scalar(low_q) or 0)
    stores_n = _store_count(db, wid)

    kpis = [
        DashboardKpi(
            label="SKUs on hand",
            value=f"{skus_on_hand:,}",
            delta=f"+{max(0, recv_t - disp_t)} today",
        ),
        DashboardKpi(
            label="Dispatched today",
            value=f"{disp_t:,}",
            delta=delta_pct(float(disp_t), float(disp_y)),
        ),
        DashboardKpi(
            label="Received today",
            value=f"{recv_t:,}",
            delta=delta_pct(float(recv_t), float(recv_y)),
        ),
        DashboardKpi(
            label="Linked stores",
            value=str(stores_n),
            delta=f"{low_t} low-stock SKUs",
        ),
    ]

    day_col = cast(func.coalesce(Grn.received_at, Grn.created_at), Date)
    inb_q = (
        select(day_col.label("d"), func.coalesce(func.sum(GrnItem.qty_received), 0))
        .select_from(GrnItem)
        .join(Grn, Grn.id == GrnItem.grn_id)
        .where(func.coalesce(Grn.received_at, Grn.created_at) >= week_start)
        .group_by(day_col)
    )
    if wid is not None:
        inb_q = inb_q.where(Grn.warehouse_id == wid)
    inb_map = {r[0]: float(r[1] or 0) for r in db.execute(inb_q).all() if r[0]}

    out_day = cast(DispatchOrder.created_at, Date)
    out_q = (
        select(out_day.label("d"), func.coalesce(func.sum(DispatchOrderItem.qty), 0))
        .select_from(DispatchOrderItem)
        .join(DispatchOrder, DispatchOrder.id == DispatchOrderItem.dispatch_order_id)
        .where(DispatchOrder.created_at >= week_start)
        .group_by(out_day)
    )
    if wid is not None:
        out_q = out_q.where(DispatchOrder.warehouse_id == wid)
    out_map = {r[0]: float(r[1] or 0) for r in db.execute(out_q).all() if r[0]}

    throughput = [
        ThroughputPoint(
            d=(week_start + timedelta(days=i)).date().strftime("%a"),
            inb=inb_map.get((week_start + timedelta(days=i)).date(), 0),
            out=out_map.get((week_start + timedelta(days=i)).date(), 0),
        )
        for i in range(7)
    ]

    zone_q = (
        select(
            func.coalesce(Category.name, "Other"),
            func.coalesce(func.sum(WarehouseInventory.on_hand), 0),
        )
        .select_from(WarehouseInventory)
        .join(ProductVariant, ProductVariant.id == WarehouseInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .group_by(Category.name)
        .order_by(func.sum(WarehouseInventory.on_hand).desc())
        .limit(5)
    )
    if wid is not None:
        zone_q = zone_q.where(WarehouseInventory.warehouse_id == wid)
    zone_rows = db.execute(zone_q).all()
    total_zone = sum(float(r[1] or 0) for r in zone_rows) or 1.0
    prefixes = ["A", "B", "C", "D", "E"]
    zones = [
        ZoneUse(
            zone=f"{prefixes[i]} · {r[0]}",
            used=round(float(r[1] or 0) / total_zone * 100, 0),
        )
        for i, r in enumerate(zone_rows)
    ]

    grn_q = (
        select(
            Grn.grn_number,
            Supplier.name,
            Grn.status,
            func.coalesce(Grn.received_at, Grn.created_at),
            func.coalesce(func.sum(GrnItem.qty_received), 0),
        )
        .outerjoin(PurchaseOrder, PurchaseOrder.id == Grn.purchase_order_id)
        .outerjoin(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .outerjoin(GrnItem, GrnItem.grn_id == Grn.id)
        .group_by(Grn.id, Supplier.name)
        .order_by(func.coalesce(Grn.received_at, Grn.created_at).desc())
        .limit(4)
    )
    if wid is not None:
        grn_q = grn_q.where(Grn.warehouse_id == wid)

    do_q = (
        select(
            DispatchOrder.do_number,
            DispatchOrder.destination_label,
            DispatchOrder.status,
            DispatchOrder.created_at,
            func.coalesce(func.sum(DispatchOrderItem.qty), 0),
        )
        .outerjoin(
            DispatchOrderItem, DispatchOrderItem.dispatch_order_id == DispatchOrder.id
        )
        .group_by(DispatchOrder.id)
        .order_by(DispatchOrder.created_at.desc())
        .limit(4)
    )
    if wid is not None:
        do_q = do_q.where(DispatchOrder.warehouse_id == wid)

    tr_q = (
        select(
            StockTransfer.transfer_number,
            StockTransfer.status,
            StockTransfer.created_at,
        )
        .order_by(StockTransfer.created_at.desc())
        .limit(3)
    )
    if wid is not None:
        tr_q = tr_q.where(StockTransfer.from_warehouse_id == wid)

    activity: list[tuple] = []
    for r in db.execute(grn_q).all():
        st = r[2] or "Pending"
        activity.append(
            (
                r[3],
                WarehouseActivity(
                    id=r[0],
                    type="Receiving",
                    vendor=r[1] or "Supplier",
                    qty=int(r[4] or 0),
                    status="Done"
                    if st.lower() in ("done", "completed", "received")
                    else st,
                ),
            )
        )
    for r in db.execute(do_q).all():
        activity.append(
            (
                r[3],
                WarehouseActivity(
                    id=r[0],
                    type="Dispatch",
                    vendor=r[1] or "Store",
                    qty=int(r[4] or 0),
                    status=r[2] or "Pending",
                ),
            )
        )
    for r in db.execute(tr_q).all():
        activity.append(
            (
                r[2],
                WarehouseActivity(
                    id=r[0],
                    type="Transfer",
                    vendor="Internal",
                    qty=0,
                    status=(r[1] or "pending").replace("_", " ").title(),
                ),
            )
        )
    activity.sort(key=lambda x: x[0] or today, reverse=True)

    return StaffWarehouseDashboardResponse(
        kpis=kpis,
        throughput=throughput,
        zones=zones,
        recentActivity=[a[1] for a in activity[:5]],
    )
