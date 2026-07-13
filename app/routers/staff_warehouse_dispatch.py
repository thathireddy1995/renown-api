"""Staff warehouse dispatch — /staff/warehouse/dispatch."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role
from app.dto.staff_dto import (
    StaffDispatchCreate,
    StaffDispatchListResponse,
    StaffDispatchOut,
)
from app.schemas import (
    DispatchOrder,
    DispatchOrderItem,
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


def _default_warehouse(db: Session) -> Warehouse | None:
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def _dispatch_out(d: DispatchOrder) -> StaffDispatchOut:
    items = d.items or []
    return StaffDispatchOut(
        id=d.do_number,
        destination=d.destination_label or "",
        type=TYPE_LABEL.get(d.destination_type, d.destination_type),
        carrier=d.carrier or "",
        awb=d.awb or "",
        items=sum(i.qty for i in items),
        status=d.status,
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
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffDispatchListResponse:
    limit, offset = page
    stmt = select(DispatchOrder).options(selectinload(DispatchOrder.items))
    count_stmt = select(func.count()).select_from(DispatchOrder)

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
    _: User = Depends(get_current_warehouse_staff),
) -> StaffDispatchOut:
    warehouse_id = body.warehouse_id
    if warehouse_id is None:
        wh = _default_warehouse(db)
        if not wh:
            raise HTTPException(status_code=400, detail="No warehouse configured")
        warehouse_id = wh.id
    elif not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")

    dest_type = body.destination_type
    if dest_type not in ("store_replen", "d2c"):
        # accept UI labels
        low = dest_type.lower()
        if "replen" in low or "store" in low:
            dest_type = "store_replen"
        elif "d2c" in low:
            dest_type = "d2c"
        else:
            raise HTTPException(status_code=422, detail="Invalid destination_type")

    label = body.destination_label
    if not label and body.destination_id and dest_type == "store_replen":
        store = db.get(Store, body.destination_id)
        if store:
            label = store.name

    if not body.items:
        raise HTTPException(status_code=422, detail="At least one item required")

    for it in body.items:
        if not db.get(ProductVariant, it.variant_id):
            raise HTTPException(
                status_code=404, detail=f"Variant {it.variant_id} not found"
            )

    do_number = f"DO-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(DispatchOrder.id).where(DispatchOrder.do_number == do_number)):
        do_number = f"DO-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    order = DispatchOrder(
        do_number=do_number,
        warehouse_id=warehouse_id,
        destination_type=dest_type,
        destination_id=body.destination_id,
        destination_label=label or "",
        carrier=body.carrier,
        awb=body.awb,
        status=body.status or "Pending",
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
        .options(selectinload(DispatchOrder.items))
    )
    assert loaded
    return _dispatch_out(loaded)
