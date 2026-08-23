"""Staff warehouse dispatch — /staff/warehouse/dispatch."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import TokenPrincipal
from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role
from app.core.warehouse_deliveries import (
    fulfill_online_order,
    list_pending_deliveries_query,
    next_do_number,
    pending_delivery_row,
    resolve_order,
)
from app.dto.staff_dto import (
    StaffDispatchCreate,
    StaffDispatchListResponse,
    StaffDispatchOut,
    StaffDispatchStatusUpdate,
    StaffPendingDeliveryListResponse,
    StaffPendingDeliveryOut,
)
from app.schemas import (
    DispatchOrder,
    DispatchOrderItem,
    Order,
    ProductVariant,
    Store,
    User,
    Warehouse,
    WarehouseInventory,
)

router = APIRouter(prefix="/staff/warehouse/dispatch", tags=["staff-warehouse-dispatch"], dependencies=[Depends(require_role("warehouse_manager"))])

TYPE_LABEL = {
    "store_replen": "Store Replen",
    "d2c": "D2C Order",
}


def _jwt_warehouse(db: Session, principal: TokenPrincipal) -> Warehouse:
    if principal.warehouse_id is not None:
        wh = db.get(Warehouse, principal.warehouse_id)
        if wh:
            return wh
    wh = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
    if not wh:
        raise HTTPException(status_code=400, detail="No warehouse configured")
    return wh


def _assert_owned_store(db: Session, warehouse_id: int, store_id: int) -> Store:
    store = db.get(Store, store_id)
    if not store or store.warehouse_id != warehouse_id:
        raise HTTPException(
            status_code=404, detail="Store not found for this warehouse"
        )
    return store


def _dispatch_out(d: DispatchOrder, items_override: int | None = None) -> StaffDispatchOut:
    items = d.items or []
    qty = items_override if items_override is not None else sum(i.qty for i in items)
    order_number = d.order.order_number if getattr(d, "order", None) else None
    return StaffDispatchOut(
        id=d.do_number,
        destination=d.destination_label or "",
        type=TYPE_LABEL.get(d.destination_type, d.destination_type),
        carrier=d.carrier or "",
        awb=d.awb or "",
        items=qty,
        status=d.status,
        order=order_number,
    )


def _normalize_status(raw: str | None) -> str:
    key = (raw or "Pending").strip().lower()
    if key in ("pending", "open", "queued"):
        return "Pending"
    if key in ("processing", "in progress", "in_transit", "in transit", "shipped"):
        return "Processing"
    if key in ("done", "completed", "complete", "delivered"):
        return "Done"
    if key in ("cancelled", "canceled", "void"):
        return "Cancelled"
    return "Pending"


def _resolve_dispatch(db: Session, do_ref: str) -> DispatchOrder | None:
    stmt = select(DispatchOrder).options(
        selectinload(DispatchOrder.items), selectinload(DispatchOrder.order)
    )
    row = db.scalar(stmt.where(DispatchOrder.do_number == do_ref))
    if row:
        return row
    if do_ref.isdigit():
        return db.scalar(stmt.where(DispatchOrder.id == int(do_ref)))
    return None


@router.get("/pending-orders", response_model=StaffPendingDeliveryListResponse)
def list_pending_online_orders(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffPendingDeliveryListResponse:
    limit, offset = page
    stmt, count_stmt = list_pending_deliveries_query(search=search)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Order.id.desc()).limit(limit).offset(offset)
    ).all()
    return StaffPendingDeliveryListResponse(
        items=[StaffPendingDeliveryOut.model_validate(pending_delivery_row(o)) for o in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _decrement_inventory(
    db: Session, warehouse_id: int, variant_id: int, qty: int
) -> None:
    if qty <= 0:
        return
    row = db.scalar(
        select(WarehouseInventory).where(
            WarehouseInventory.warehouse_id == warehouse_id,
            WarehouseInventory.variant_id == variant_id,
        )
    )
    if not row:
        raise HTTPException(
            status_code=400,
            detail=f"No warehouse inventory for variant {variant_id}",
        )
    if int(row.on_hand or 0) < qty:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient stock for variant {variant_id}",
        )
    row.on_hand = int(row.on_hand) - qty


@router.get("", response_model=StaffDispatchListResponse)
def list_dispatches(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffDispatchListResponse:
    limit, offset = page
    wid = _jwt_warehouse(db, principal).id
    stmt = (
        select(DispatchOrder)
        .options(selectinload(DispatchOrder.items), selectinload(DispatchOrder.order))
        .where(DispatchOrder.warehouse_id == wid)
    )
    count_stmt = (
        select(func.count())
        .select_from(DispatchOrder)
        .where(DispatchOrder.warehouse_id == wid)
    )

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            DispatchOrder.do_number.ilike(like),
            DispatchOrder.destination_label.ilike(like),
            DispatchOrder.carrier.ilike(like),
            DispatchOrder.awb.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(DispatchOrder.id.desc()).limit(limit).offset(offset)
    ).all()
    return StaffDispatchListResponse(
        items=[_dispatch_out(d) for d in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffDispatchOut, status_code=status.HTTP_201_CREATED)
def create_dispatch(
    body: StaffDispatchCreate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffDispatchOut:
    warehouse_id = _jwt_warehouse(db, principal).id

    dest_type = body.destination_type
    if dest_type not in ("store_replen", "d2c"):
        low = dest_type.lower()
        if "replen" in low or ("store" in low and "return" not in low):
            dest_type = "store_replen"
        elif "d2c" in low or "online" in low or "order" in low:
            dest_type = "d2c"
        else:
            raise HTTPException(status_code=422, detail="Invalid destination_type")

    if dest_type == "d2c" and (body.order_ref or body.destination_id):
        order_ref = body.order_ref or str(body.destination_id)
        order = resolve_order(db, order_ref)
        if not order:
            raise HTTPException(status_code=404, detail="Online order not found")
        dispatch = fulfill_online_order(
            db,
            warehouse_id=warehouse_id,
            order=order,
            carrier=body.carrier,
            awb=body.awb,
            mark_shipped=True,
        )
        return _dispatch_out(dispatch)

    destination_id = body.destination_id
    label = body.destination_label
    if dest_type == "store_replen":
        if destination_id is not None:
            store = _assert_owned_store(db, warehouse_id, destination_id)
            label = label or store.name
        elif label:
            store = db.scalar(
                select(Store).where(
                    Store.warehouse_id == warehouse_id,
                    Store.name.ilike(label.strip()),
                ).limit(1)
            )
            if not store:
                raise HTTPException(
                    status_code=404, detail="Store not found for this warehouse"
                )
            destination_id = store.id
            label = store.name
        else:
            raise HTTPException(status_code=422, detail="Select a store destination")

    if not body.items:
        raise HTTPException(
            status_code=422,
            detail="Select a SKU and quantity, or pick an online order to dispatch",
        )

    for it in body.items:
        if not db.get(ProductVariant, it.variant_id):
            raise HTTPException(
                status_code=404, detail=f"Variant {it.variant_id} not found"
            )

    order = DispatchOrder(
        do_number=next_do_number(db),
        warehouse_id=warehouse_id,
        destination_type=dest_type,
        destination_id=destination_id,
        destination_label=label or "",
        carrier=body.carrier,
        awb=body.awb,
        status=_normalize_status(body.status),
    )
    db.add(order)
    db.flush()

    for it in body.items:
        db.add(
            DispatchOrderItem(
                dispatch_order_id=order.id,
                variant_id=it.variant_id,
                qty=it.qty,
            )
        )
        _decrement_inventory(db, warehouse_id, it.variant_id, it.qty)

    db.commit()
    loaded = db.scalar(
        select(DispatchOrder)
        .where(DispatchOrder.id == order.id)
        .options(selectinload(DispatchOrder.items), selectinload(DispatchOrder.order))
    )
    assert loaded
    return _dispatch_out(loaded)


@router.patch("/{do_ref}/status", response_model=StaffDispatchOut)
def patch_dispatch_status(
    do_ref: str,
    body: StaffDispatchStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffDispatchOut:
    order = _resolve_dispatch(db, do_ref)
    if not order:
        raise HTTPException(status_code=404, detail="Dispatch order not found")
    order.status = _normalize_status(body.status)
    db.commit()
    db.refresh(order)
    return _dispatch_out(order)
