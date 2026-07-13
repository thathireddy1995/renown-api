"""Staff warehouse transfers — /staff/warehouse/transfers."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.stock_transfers import (
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
)
from app.schemas import ProductVariant, StockTransfer, StockTransferItem, User, Warehouse

router = APIRouter(
    prefix="/staff/warehouse/transfers", tags=["staff-warehouse-transfers"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


def _out(row: dict) -> StaffStockTransferOut:
    return StaffStockTransferOut.model_validate(
        {"from": row["from"], **{k: v for k, v in row.items() if k != "from"}}
    )


def _default_warehouse(db: Session) -> Warehouse | None:
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


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
    if from_id is None:
        wh = _default_warehouse(db)
        if not wh:
            raise HTTPException(status_code=400, detail="No warehouse configured")
        from_id = wh.id
    if not body.to_warehouse_id and not body.to_store_id:
        raise HTTPException(status_code=422, detail="Destination required")
    if not body.items:
        raise HTTPException(status_code=422, detail="At least one item required")

    for it in body.items:
        if not db.get(ProductVariant, it.variant_id):
            raise HTTPException(status_code=404, detail=f"Variant {it.variant_id} not found")

    num = f"TR-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(StockTransfer.id).where(StockTransfer.transfer_number == num)):
        num = f"TR-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    transfer = StockTransfer(
        transfer_number=num,
        from_warehouse_id=from_id,
        to_warehouse_id=body.to_warehouse_id,
        to_store_id=body.to_store_id,
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
    return _out(staff_transfer_row(loaded))
