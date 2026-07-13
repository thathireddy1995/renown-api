"""Staff warehouse receiving — /staff/warehouse/receiving."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.relative_time import relative_received_label
from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination
from app.dto.staff_dto import (
    StaffGrnCreate,
    StaffGrnListResponse,
    StaffGrnOut,
)
from app.schemas import (
    Grn,
    GrnItem,
    ProductVariant,
    PurchaseOrder,
    Supplier,
    User,
    Warehouse,
    WarehouseInventory,
)

router = APIRouter(prefix="/staff/warehouse/receiving", tags=["staff-warehouse-receiving"])


def _default_warehouse(db: Session) -> Warehouse | None:
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def _grn_out(g: Grn) -> StaffGrnOut:
    po = g.purchase_order
    vendor = po.supplier.name if po and po.supplier else ""
    items = g.items or []
    return StaffGrnOut(
        id=g.grn_number,
        po=po.po_number if po else "",
        vendor=vendor,
        items=len(items),
        qty=sum(i.qty_received for i in items),
        date=relative_received_label(g.received_at or g.created_at),
        status=g.status,
    )


def _bump_inventory(
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
    if row:
        row.on_hand = int(row.on_hand or 0) + qty
    else:
        db.add(
            WarehouseInventory(
                warehouse_id=warehouse_id,
                variant_id=variant_id,
                on_hand=qty,
                reserved=0,
                reorder_point=0,
            )
        )


@router.get("", response_model=StaffGrnListResponse)
def list_grns(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffGrnListResponse:
    limit, offset = page
    stmt = (
        select(Grn)
        .options(
            selectinload(Grn.items),
            selectinload(Grn.purchase_order).selectinload(PurchaseOrder.supplier),
        )
        .join(PurchaseOrder, PurchaseOrder.id == Grn.purchase_order_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
    )
    count_stmt = (
        select(func.count())
        .select_from(Grn)
        .join(PurchaseOrder, PurchaseOrder.id == Grn.purchase_order_id)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
    )

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            Grn.grn_number.ilike(like),
            PurchaseOrder.po_number.ilike(like),
            Supplier.name.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Grn.id.desc()).limit(limit).offset(offset)
    ).all()
    return StaffGrnListResponse(
        items=[_grn_out(g) for g in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffGrnOut, status_code=status.HTTP_201_CREATED)
def create_grn(
    body: StaffGrnCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffGrnOut:
    warehouse_id = body.warehouse_id
    if warehouse_id is None:
        wh = _default_warehouse(db)
        if not wh:
            raise HTTPException(status_code=400, detail="No warehouse configured")
        warehouse_id = wh.id
    elif not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")

    po: PurchaseOrder | None = None
    if body.purchase_order_id:
        po = db.get(PurchaseOrder, body.purchase_order_id)
    elif body.po_number:
        po = db.scalar(
            select(PurchaseOrder).where(PurchaseOrder.po_number == body.po_number)
        )

    if not po:
        if not body.supplier_id:
            raise HTTPException(
                status_code=422, detail="purchase_order_id or supplier_id required"
            )
        if not db.get(Supplier, body.supplier_id):
            raise HTTPException(status_code=404, detail="Supplier not found")
        po_num = body.po_number or f"PO-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
        po = PurchaseOrder(
            po_number=po_num,
            supplier_id=body.supplier_id,
            status="Open",
        )
        db.add(po)
        db.flush()

    if not body.items:
        raise HTTPException(status_code=422, detail="At least one item required")

    for it in body.items:
        if not db.get(ProductVariant, it.variant_id):
            raise HTTPException(
                status_code=404, detail=f"Variant {it.variant_id} not found"
            )

    grn_number = f"GRN-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(Grn.id).where(Grn.grn_number == grn_number)):
        grn_number = f"GRN-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    status_val = body.status or "Done"
    now = datetime.now(timezone.utc)
    grn = Grn(
        grn_number=grn_number,
        purchase_order_id=po.id,
        warehouse_id=warehouse_id,
        status=status_val,
        received_at=now if status_val == "Done" else None,
    )
    db.add(grn)
    db.flush()

    for it in body.items:
        db.add(
            GrnItem(
                grn_id=grn.id,
                variant_id=it.variant_id,
                qty_ordered=it.qty_ordered,
                qty_received=it.qty_received,
            )
        )
        if status_val == "Done":
            _bump_inventory(db, warehouse_id, it.variant_id, it.qty_received)

    if status_val == "Done":
        po.status = "Received"

    db.commit()

    loaded = db.scalar(
        select(Grn)
        .where(Grn.id == grn.id)
        .options(
            selectinload(Grn.items),
            selectinload(Grn.purchase_order).selectinload(PurchaseOrder.supplier),
        )
    )
    assert loaded
    return _grn_out(loaded)
