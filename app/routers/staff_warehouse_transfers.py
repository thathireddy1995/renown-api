"""Staff warehouse transfers — /staff/warehouse/transfers."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.stock_transfers import (
    apply_transfer_completion,
    list_stock_transfers_query,
    normalize_transfer_status,
    staff_transfer_row,
    transfer_eager_options,
)
from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role
from app.dto.staff_dto import (
    StaffStockTransferCreate,
    StaffStockTransferListResponse,
    StaffStockTransferOut,
    StaffStockTransferStatusUpdate,
)
from app.schemas import ProductVariant, StockTransfer, StockTransferItem, Store, User, Warehouse

router = APIRouter(
    prefix="/staff/warehouse/transfers",
    tags=["staff-warehouse-transfers"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


def _out(row: dict) -> StaffStockTransferOut:
    return StaffStockTransferOut.model_validate(
        {"from": row["from"], **{k: v for k, v in row.items() if k != "from"}}
    )


def _default_warehouse(db: Session) -> Warehouse | None:
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def _resolve_warehouse_by_name(db: Session, name: str) -> Warehouse | None:
    if not name.strip():
        return None
    return db.scalar(
        select(Warehouse).where(Warehouse.name.ilike(name.strip())).limit(1)
    )


def _resolve_store_by_name(db: Session, name: str) -> Store | None:
    if not name.strip():
        return None
    return db.scalar(select(Store).where(Store.name.ilike(name.strip())).limit(1))


def _resolve_transfer(db: Session, transfer_ref: str) -> StockTransfer | None:
    stmt = select(StockTransfer).options(*transfer_eager_options())
    row = db.scalar(stmt.where(StockTransfer.transfer_number == transfer_ref))
    if row:
        return row
    if transfer_ref.isdigit():
        return db.scalar(stmt.where(StockTransfer.id == int(transfer_ref)))
    return None


@router.get("", response_model=StaffStockTransferListResponse)
def list_transfers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
    warehouse_id: int | None = None,
) -> StaffStockTransferListResponse:
    limit, offset = page
    stmt, count_stmt = list_stock_transfers_query(
        search=search, from_warehouse_id=warehouse_id
    )
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(StockTransfer.id.desc()).limit(limit).offset(offset)
    ).all()
    return StaffStockTransferListResponse(
        items=[_out(staff_transfer_row(t)) for t in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffStockTransferOut, status_code=status.HTTP_201_CREATED)
def create_transfer(
    body: StaffStockTransferCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffStockTransferOut:
    from_id = body.from_warehouse_id
    if from_id is None and body.from_label:
        wh = _resolve_warehouse_by_name(db, body.from_label)
        if wh:
            from_id = wh.id
    if from_id is None:
        wh = _default_warehouse(db)
        if not wh:
            raise HTTPException(status_code=400, detail="No warehouse configured")
        from_id = wh.id
    elif not db.get(Warehouse, from_id):
        raise HTTPException(status_code=404, detail="Source warehouse not found")

    to_wh_id = body.to_warehouse_id
    to_store_id = body.to_store_id
    dest_type = (body.destination_type or "").strip().lower()

    if not to_wh_id and not to_store_id and body.to_label:
        if dest_type in ("store", "store_replen", "retail"):
            store = _resolve_store_by_name(db, body.to_label)
            if store:
                to_store_id = store.id
            else:
                wh = _resolve_warehouse_by_name(db, body.to_label)
                if wh:
                    to_wh_id = wh.id
        else:
            wh = _resolve_warehouse_by_name(db, body.to_label)
            if wh:
                to_wh_id = wh.id
            else:
                store = _resolve_store_by_name(db, body.to_label)
                if store:
                    to_store_id = store.id

    if not to_wh_id and not to_store_id:
        raise HTTPException(status_code=422, detail="Destination required")

    for it in body.items:
        if not db.get(ProductVariant, it.variant_id):
            raise HTTPException(status_code=404, detail=f"Variant {it.variant_id} not found")

    num = f"TR-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(StockTransfer.id).where(StockTransfer.transfer_number == num)):
        num = f"TR-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    transfer = StockTransfer(
        transfer_number=num,
        from_warehouse_id=from_id,
        to_warehouse_id=to_wh_id,
        to_store_id=to_store_id,
        status=normalize_transfer_status(body.status),
    )
    db.add(transfer)
    db.flush()
    for it in body.items:
        db.add(
            StockTransferItem(
                stock_transfer_id=transfer.id,
                variant_id=it.variant_id,
                qty=it.qty,
            )
        )
    db.commit()
    loaded = db.scalar(
        select(StockTransfer)
        .where(StockTransfer.id == transfer.id)
        .options(*transfer_eager_options())
    )
    assert loaded
    items_override = None
    qty_override = None
    if not body.items:
        if body.items_count is not None:
            items_override = max(0, int(body.items_count))
        if body.qty is not None:
            qty_override = max(0, int(body.qty))
    return _out(
        staff_transfer_row(
            loaded, items_override=items_override, qty_override=qty_override
        )
    )


@router.patch("/{transfer_ref}/status", response_model=StaffStockTransferOut)
def patch_transfer_status(
    transfer_ref: str,
    body: StaffStockTransferStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffStockTransferOut:
    transfer = _resolve_transfer(db, transfer_ref)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    new_status = normalize_transfer_status(body.status)
    old = transfer.status
    transfer.status = new_status

    if new_status == "completed" and old != "completed":
        apply_transfer_completion(db, transfer)

    db.commit()
    refreshed = _resolve_transfer(db, transfer_ref)
    assert refreshed
    return _out(staff_transfer_row(refreshed))
