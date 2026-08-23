"""Staff warehouse transfers — /staff/warehouse/transfers."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.stock_transfers import (
    apply_transfer_completion,
    list_stock_transfers_query,
    normalize_transfer_status,
    persist_stock_transfer,
    staff_transfer_row,
    transfer_eager_options,
)
from app.core.deps import TokenPrincipal
from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role
from app.dto.staff_dto import (
    StaffStockTransferCreate,
    StaffStockTransferListResponse,
    StaffStockTransferOut,
    StaffStockTransferStatusUpdate,
)
from app.schemas import StockTransfer, Store, User, Warehouse

router = APIRouter(
    prefix="/staff/warehouse/transfers",
    tags=["staff-warehouse-transfers"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


def _out(row: dict) -> StaffStockTransferOut:
    return StaffStockTransferOut.model_validate(
        {"from": row["from"], **{k: v for k, v in row.items() if k != "from"}}
    )


def _jwt_warehouse(db: Session, principal: TokenPrincipal) -> Warehouse:
    if principal.warehouse_id is not None:
        wh = db.get(Warehouse, principal.warehouse_id)
        if wh:
            return wh
    wh = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
    if not wh:
        raise HTTPException(status_code=400, detail="No warehouse configured")
    return wh


def _resolve_warehouse_by_name(db: Session, name: str) -> Warehouse | None:
    if not name.strip():
        return None
    return db.scalar(
        select(Warehouse).where(Warehouse.name.ilike(name.strip())).limit(1)
    )


def _resolve_store_by_name(db: Session, name: str, warehouse_id: int) -> Store | None:
    if not name.strip():
        return None
    return db.scalar(
        select(Store)
        .where(
            Store.warehouse_id == warehouse_id,
            Store.name.ilike(name.strip()),
        )
        .limit(1)
    )


def _assert_owned_store(db: Session, warehouse_id: int, store_id: int) -> Store:
    store = db.get(Store, store_id)
    if not store or store.warehouse_id != warehouse_id:
        raise HTTPException(
            status_code=404, detail="Store not found for this warehouse"
        )
    return store


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
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffStockTransferListResponse:
    limit, offset = page
    wid = _jwt_warehouse(db, principal).id
    stmt, count_stmt = list_stock_transfers_query(
        search=search, warehouse_id=wid
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
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffStockTransferOut:
    my_wh = _jwt_warehouse(db, principal)
    dest_type = (body.destination_type or "").strip().lower()
    from_store_id = body.from_store_id
    to_wh_id = body.to_warehouse_id
    to_store_id = body.to_store_id
    from_wh_id: int | None = my_wh.id

    if dest_type in ("store_return", "return", "store_to_wh"):
        from_wh_id = None
        to_wh_id = my_wh.id
        if from_store_id is None and body.to_label:
            store = _resolve_store_by_name(db, body.to_label, my_wh.id)
            if store:
                from_store_id = store.id
        if from_store_id is None:
            raise HTTPException(status_code=422, detail="Select the store returning stock")
        _assert_owned_store(db, my_wh.id, from_store_id)
        to_store_id = None
    else:
        if to_store_id is not None:
            _assert_owned_store(db, my_wh.id, to_store_id)

        if not to_wh_id and not to_store_id and body.to_label:
            if dest_type in ("store", "store_replen", "retail"):
                store = _resolve_store_by_name(db, body.to_label, my_wh.id)
                if store:
                    to_store_id = store.id
                else:
                    raise HTTPException(
                        status_code=404,
                        detail="Store not found for this warehouse",
                    )
            else:
                wh = _resolve_warehouse_by_name(db, body.to_label)
                if wh:
                    to_wh_id = wh.id
                else:
                    store = _resolve_store_by_name(db, body.to_label, my_wh.id)
                    if store:
                        to_store_id = store.id

        if not to_wh_id and not to_store_id:
            raise HTTPException(status_code=422, detail="Destination required")
        if to_store_id is not None:
            _assert_owned_store(db, my_wh.id, to_store_id)

    if not body.items:
        raise HTTPException(status_code=422, detail="Select a SKU and quantity")

    loaded = persist_stock_transfer(
        db,
        from_warehouse_id=from_wh_id,
        from_store_id=from_store_id,
        to_warehouse_id=to_wh_id,
        to_store_id=to_store_id,
        items=body.items,
        status=body.status,
    )
    return _out(staff_transfer_row(loaded))


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
