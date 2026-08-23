"""Admin warehouse stock transfers — /admin/warehouse/transfers."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.stock_transfers import (
    ADMIN_STATUS,
    admin_transfer_row,
    apply_transfer_completion,
    list_stock_transfers_query,
    normalize_transfer_status,
    persist_stock_transfer,
    transfer_eager_options,
)
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminStockTransferCreate,
    AdminStockTransferListResponse,
    AdminStockTransferOut,
    AdminStockTransferStatusUpdate,
)
from app.schemas import StockTransfer, Store, Warehouse

router = APIRouter(prefix="/admin/warehouse/transfers", tags=["admin-warehouse-transfers"], dependencies=[Depends(require_role("admin"))])


def _out(row: dict) -> AdminStockTransferOut:
    return AdminStockTransferOut.model_validate(
        {"from": row["from"], **{k: v for k, v in row.items() if k != "from"}}
    )


@router.get("", response_model=AdminStockTransferListResponse)
def list_transfers(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> AdminStockTransferListResponse:
    limit, offset = page
    stmt, count_stmt = list_stock_transfers_query(
        status=status_filter, search=search
    )
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(StockTransfer.id.desc()).limit(limit).offset(offset)
    ).all()

    # Tab counts in one GROUP BY
    count_rows = db.execute(
        select(StockTransfer.status, func.count()).group_by(StockTransfer.status)
    ).all()
    counts = {"All": 0}
    for s, n in count_rows:
        label = ADMIN_STATUS.get(s, s)
        counts[label] = int(n)
        counts["All"] += int(n)

    return AdminStockTransferListResponse(
        items=[_out(admin_transfer_row(t)) for t in rows],
        total=total,
        limit=limit,
        offset=offset,
        counts=counts,
    )


@router.post("", response_model=AdminStockTransferOut, status_code=status.HTTP_201_CREATED)
def create_transfer(
    body: AdminStockTransferCreate, db: Session = Depends(get_db)
) -> AdminStockTransferOut:
    if body.from_warehouse_id and not db.get(Warehouse, body.from_warehouse_id):
        raise HTTPException(status_code=404, detail="Source warehouse not found")
    if body.to_warehouse_id and not db.get(Warehouse, body.to_warehouse_id):
        raise HTTPException(status_code=404, detail="Destination warehouse not found")
    if body.from_store_id and not db.get(Store, body.from_store_id):
        raise HTTPException(status_code=404, detail="Source store not found")
    if body.to_store_id and not db.get(Store, body.to_store_id):
        raise HTTPException(status_code=404, detail="Destination store not found")

    eta = None
    if body.eta and body.eta != "—":
        eta = date.fromisoformat(body.eta[:10])

    loaded = persist_stock_transfer(
        db,
        from_warehouse_id=body.from_warehouse_id,
        from_store_id=body.from_store_id,
        to_warehouse_id=body.to_warehouse_id,
        to_store_id=body.to_store_id,
        items=body.items,
        status=body.status,
        requested_by=body.requested_by,
        eta=eta,
    )
    return _out(admin_transfer_row(loaded))


def _resolve(db: Session, transfer_ref: str) -> StockTransfer | None:
    stmt = select(StockTransfer).options(*transfer_eager_options())
    row = db.scalar(stmt.where(StockTransfer.transfer_number == transfer_ref))
    if row:
        return row
    if transfer_ref.isdigit():
        return db.scalar(stmt.where(StockTransfer.id == int(transfer_ref)))
    return None


@router.patch("/{transfer_ref}/status", response_model=AdminStockTransferOut)
def update_transfer_status(
    transfer_ref: str,
    body: AdminStockTransferStatusUpdate,
    db: Session = Depends(get_db),
) -> AdminStockTransferOut:
    transfer = _resolve(db, transfer_ref)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")

    new_status = normalize_transfer_status(body.status)
    old = transfer.status
    transfer.status = new_status

    if new_status == "completed" and old != "completed":
        apply_transfer_completion(db, transfer)

    db.commit()
    refreshed = _resolve(db, transfer_ref)
    assert refreshed
    return _out(admin_transfer_row(refreshed))
