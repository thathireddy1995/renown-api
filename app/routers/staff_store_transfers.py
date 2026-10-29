"""Staff store incoming transfers — /staff/store/transfers.

The warehouse pushes stock to a store as a StockTransfer (status ``in_transit``).
Stock only lands in store inventory once the store taps **Receive** here, which
completes the transfer and runs the warehouse->store stock movement.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.stock_transfers import (
    apply_transfer_completion,
    staff_status_label,
    transfer_from_name,
)
from app.core.ist import now as ist_now
from app.database import get_db
from app.deps import require_role, TokenPrincipal
from app.schemas import (
    Product,
    ProductVariant,
    Store,
    StockTransfer,
    StockTransferItem,
)

router = APIRouter(
    prefix="/staff/store/transfers",
    tags=["staff-store-transfers"],
    dependencies=[Depends(require_role("store_manager"))],
)

# Transfers in any of these states are still on their way to the store (DB keys,
# everything short of completed/received/rejected).
OPEN_STATUSES = ("requested", "approved", "picking", "packing", "in_transit")


def _resolve_store(db: Session, principal: TokenPrincipal, store_id: int | None) -> Store | None:
    sid = principal.store_id or store_id
    if sid is not None:
        return db.get(Store, sid)
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


class TransferLineOut(BaseModel):
    sku: str
    product: str
    qty: int


class StoreTransferOut(BaseModel):
    id: str
    from_warehouse: str
    status: str
    received: bool
    receivable: bool
    items: int
    qty: int
    created: str | None = None
    lines: list[TransferLineOut]


class StoreTransferListResponse(BaseModel):
    items: list[StoreTransferOut]
    store_id: int
    store_name: str


def _eager():
    return (
        selectinload(StockTransfer.items)
        .selectinload(StockTransferItem.variant)
        .selectinload(ProductVariant.product),
        selectinload(StockTransfer.from_warehouse),
    )


def _to_out(t: StockTransfer) -> StoreTransferOut:
    items = t.items or []
    lines = [
        TransferLineOut(
            sku=(it.variant.sku if it.variant else "") or "",
            product=(
                (it.variant.product.name if it.variant and it.variant.product else None)
                or (it.variant.sku if it.variant else None)
                or "Item"
            ),
            qty=int(it.qty or 0),
        )
        for it in items
    ]
    completed = (t.status or "").lower() == "completed"
    return StoreTransferOut(
        id=t.transfer_number,
        from_warehouse=transfer_from_name(t) or "Warehouse",
        status=staff_status_label(t.status),
        received=completed,
        receivable=not completed,
        items=len(items),
        qty=sum(int(i.qty or 0) for i in items),
        created=t.created_at.isoformat() if t.created_at else None,
        lines=lines,
    )


@router.get("", response_model=StoreTransferListResponse)
def list_incoming_transfers(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    store_id: int | None = None,
    scope: str = Query("open", pattern="^(open|all)$"),
) -> StoreTransferListResponse:
    store = _resolve_store(db, principal, store_id)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")

    stmt = (
        select(StockTransfer)
        .options(*_eager())
        .where(StockTransfer.to_store_id == store.id)
        .order_by(StockTransfer.id.desc())
    )
    if scope == "open":
        stmt = stmt.where(StockTransfer.status.in_(OPEN_STATUSES))
    rows = db.scalars(stmt.limit(200)).all()
    return StoreTransferListResponse(
        items=[_to_out(t) for t in rows],
        store_id=store.id,
        store_name=store.name or "",
    )


@router.patch("/{transfer_ref}/receive", response_model=StoreTransferOut)
def receive_transfer(
    transfer_ref: str,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    store_id: int | None = None,
) -> StoreTransferOut:
    store = _resolve_store(db, principal, store_id)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")

    stmt = select(StockTransfer).options(*_eager()).where(
        StockTransfer.to_store_id == store.id
    )
    transfer = db.scalar(stmt.where(StockTransfer.transfer_number == transfer_ref))
    if transfer is None and transfer_ref.isdigit():
        transfer = db.scalar(stmt.where(StockTransfer.id == int(transfer_ref)))
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found for this store")

    if (transfer.status or "").lower() == "completed":
        raise HTTPException(status_code=409, detail="This transfer is already received")

    # Moves warehouse on_hand -> store backroom/on_hand in the same transaction.
    apply_transfer_completion(db, transfer)
    transfer.status = "completed"
    transfer.updated_at = ist_now()
    db.commit()

    refreshed = db.scalar(
        select(StockTransfer).options(*_eager()).where(StockTransfer.id == transfer.id)
    )
    assert refreshed
    return _to_out(refreshed)
