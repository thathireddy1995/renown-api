"""Shared stock-transfer query helpers + inventory moves (Phase 9)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.ist import as_ist, format_ist_date, now as ist_now
from app.schemas import (
    ProductVariant,
    StockTransfer,
    StockTransferItem,
    Store,
    StoreInventory,
    Warehouse,
    WarehouseInventory,
)

# DB stores lowercase keys; admin UI expects Title Case labels.
ADMIN_STATUS = {
    "requested": "Requested",
    "approved": "Approved",
    "picking": "Picking",
    "packing": "Packing",
    "in_transit": "In transit",
    "received": "Received",
    "completed": "Completed",
    "rejected": "Rejected",
}

ADMIN_STATUS_REVERSE = {v.lower(): k for k, v in ADMIN_STATUS.items()}
ADMIN_STATUS_REVERSE.update({k: k for k in ADMIN_STATUS})

STAFF_STATUS = {
    "requested": "Pending",
    "approved": "Processing",
    "picking": "Processing",
    "packing": "Processing",
    "in_transit": "Processing",
    "received": "Delivered",
    "completed": "Delivered",
    "rejected": "Cancelled",
}


def normalize_transfer_status(value: str) -> str:
    key = (value or "").strip().lower().replace(" ", "_")
    # Staff portal labels → DB keys
    staff_ui = {
        "pending": "requested",
        "processing": "in_transit",
        "delivered": "completed",
        "cancelled": "rejected",
        "canceled": "rejected",
        "done": "completed",
    }
    if key in staff_ui:
        return staff_ui[key]
    if key in ADMIN_STATUS:
        return key
    mapped = ADMIN_STATUS_REVERSE.get((value or "").strip().lower())
    if mapped:
        return mapped
    raise HTTPException(status_code=422, detail=f"Unknown status: {value}")


def admin_status_label(raw: str) -> str:
    return ADMIN_STATUS.get((raw or "").lower(), (raw or "Requested").replace("_", " ").title())


def staff_status_label(raw: str) -> str:
    return STAFF_STATUS.get((raw or "").lower(), "Pending")


def transfer_eager_options():
    return (
        selectinload(StockTransfer.items).selectinload(StockTransferItem.variant),
        selectinload(StockTransfer.from_warehouse),
        selectinload(StockTransfer.from_store),
        selectinload(StockTransfer.to_warehouse),
        selectinload(StockTransfer.to_store),
    )


def transfer_direction(t: StockTransfer) -> str:
    if t.from_store_id and t.to_warehouse_id:
        return "store_to_wh"
    if t.from_warehouse_id and t.to_store_id:
        return "wh_to_store"
    return "wh_to_wh"


def transfer_from_name(t: StockTransfer) -> str:
    if t.from_warehouse:
        return t.from_warehouse.name or ""
    if t.from_store:
        return t.from_store.name or ""
    return ""


def transfer_to_name(t: StockTransfer) -> str:
    if t.to_warehouse:
        return t.to_warehouse.name or ""
    if t.to_store:
        return t.to_store.name or ""
    return ""


def list_stock_transfers_query(
    *,
    status: str | None = None,
    search: str | None = None,
    warehouse_id: int | None = None,
    from_warehouse_id: int | None = None,
):
    stmt = select(StockTransfer).options(*transfer_eager_options())
    count_stmt = select(func.count()).select_from(StockTransfer)
    scoped_id = warehouse_id if warehouse_id is not None else from_warehouse_id

    if scoped_id is not None:
        filt = or_(
            StockTransfer.from_warehouse_id == scoped_id,
            StockTransfer.to_warehouse_id == scoped_id,
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    if status and status.lower() not in ("all", ""):
        db_status = normalize_transfer_status(status)
        stmt = stmt.where(StockTransfer.status == db_status)
        count_stmt = count_stmt.where(StockTransfer.status == db_status)

    if search and search.strip():
        like = f"%{search.strip()}%"
        FromWh = aliased(Warehouse)
        ToWh = aliased(Warehouse)
        FromStore = aliased(Store)
        ToStore = aliased(Store)
        stmt = (
            stmt.outerjoin(FromWh, FromWh.id == StockTransfer.from_warehouse_id)
            .outerjoin(ToWh, ToWh.id == StockTransfer.to_warehouse_id)
            .outerjoin(FromStore, FromStore.id == StockTransfer.from_store_id)
            .outerjoin(ToStore, ToStore.id == StockTransfer.to_store_id)
            .outerjoin(
                StockTransferItem,
                StockTransferItem.stock_transfer_id == StockTransfer.id,
            )
            .outerjoin(ProductVariant, ProductVariant.id == StockTransferItem.variant_id)
        )
        count_stmt = (
            count_stmt.outerjoin(FromWh, FromWh.id == StockTransfer.from_warehouse_id)
            .outerjoin(ToWh, ToWh.id == StockTransfer.to_warehouse_id)
            .outerjoin(FromStore, FromStore.id == StockTransfer.from_store_id)
            .outerjoin(ToStore, ToStore.id == StockTransfer.to_store_id)
            .outerjoin(
                StockTransferItem,
                StockTransferItem.stock_transfer_id == StockTransfer.id,
            )
            .outerjoin(ProductVariant, ProductVariant.id == StockTransferItem.variant_id)
        )
        filt = or_(
            StockTransfer.transfer_number.ilike(like),
            FromWh.name.ilike(like),
            ToWh.name.ilike(like),
            FromStore.name.ilike(like),
            ToStore.name.ilike(like),
            ProductVariant.sku.ilike(like),
        )
        stmt = stmt.where(filt).distinct()
        count_stmt = count_stmt.where(filt)

    return stmt, count_stmt


def admin_transfer_row(t: StockTransfer) -> dict:
    item = (t.items or [None])[0]
    sku = item.variant.sku if item and item.variant else ""
    qty = item.qty if item else 0
    return {
        "id": t.transfer_number,
        "from": transfer_from_name(t),
        "to": transfer_to_name(t),
        "sku": sku,
        "qty": qty,
        "status": admin_status_label(t.status),
        "eta": t.eta.isoformat() if t.eta else "—",
        "created": format_ist_date(t.created_at),
        "direction": transfer_direction(t),
    }


def staff_transfer_row(
    t: StockTransfer,
    *,
    items_override: int | None = None,
    qty_override: int | None = None,
) -> dict:
    items = t.items or []
    qty = sum(i.qty for i in items)
    return {
        "id": t.transfer_number,
        "from": transfer_from_name(t),
        "to": transfer_to_name(t),
        "items": items_override if items_override is not None else len(items),
        "qty": qty_override if qty_override is not None else qty,
        "requested": _relative_day(t.created_at),
        "status": staff_status_label(t.status),
        "direction": transfer_direction(t),
    }


def next_transfer_number(db: Session) -> str:
    base = int(ist_now().timestamp() * 1000) % 10_000_000
    for step in range(25):
        num = f"TR-{base + step}"
        if not db.scalar(select(StockTransfer.id).where(StockTransfer.transfer_number == num)):
            return num
    raise HTTPException(status_code=500, detail="Could not allocate transfer number")


def validate_transfer_legs(
    *,
    from_warehouse_id: int | None,
    from_store_id: int | None,
    to_warehouse_id: int | None,
    to_store_id: int | None,
) -> None:
    if bool(from_warehouse_id) == bool(from_store_id):
        raise HTTPException(
            status_code=422, detail="Choose exactly one source: warehouse or store"
        )
    if bool(to_warehouse_id) == bool(to_store_id):
        raise HTTPException(
            status_code=422, detail="Choose exactly one destination: warehouse or store"
        )
    if from_store_id and to_store_id:
        raise HTTPException(
            status_code=422, detail="Store-to-store transfers are not supported"
        )
    if from_warehouse_id and to_warehouse_id and from_warehouse_id == to_warehouse_id:
        raise HTTPException(status_code=422, detail="Source and destination must differ")


def persist_stock_transfer(
    db: Session,
    *,
    from_warehouse_id: int | None,
    from_store_id: int | None,
    to_warehouse_id: int | None,
    to_store_id: int | None,
    items: list,
    status: str,
    requested_by: str | None = None,
    eta: date | None = None,
) -> StockTransfer:
    validate_transfer_legs(
        from_warehouse_id=from_warehouse_id,
        from_store_id=from_store_id,
        to_warehouse_id=to_warehouse_id,
        to_store_id=to_store_id,
    )
    if not items:
        raise HTTPException(status_code=422, detail="At least one SKU line is required")

    for it in items:
        variant_id = it.variant_id if hasattr(it, "variant_id") else it["variant_id"]
        qty = it.qty if hasattr(it, "qty") else it["qty"]
        if qty <= 0:
            raise HTTPException(status_code=422, detail="Quantity must be greater than 0")
        if not db.get(ProductVariant, variant_id):
            raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")

    transfer = StockTransfer(
        transfer_number=next_transfer_number(db),
        from_warehouse_id=from_warehouse_id,
        from_store_id=from_store_id,
        to_warehouse_id=to_warehouse_id,
        to_store_id=to_store_id,
        status=normalize_transfer_status(status),
        requested_by=requested_by,
        eta=eta,
    )
    db.add(transfer)
    db.flush()
    for it in items:
        variant_id = it.variant_id if hasattr(it, "variant_id") else it["variant_id"]
        qty = it.qty if hasattr(it, "qty") else it["qty"]
        db.add(
            StockTransferItem(
                stock_transfer_id=transfer.id,
                variant_id=variant_id,
                qty=qty,
            )
        )
    db.commit()
    loaded = db.scalar(
        select(StockTransfer)
        .where(StockTransfer.id == transfer.id)
        .options(*transfer_eager_options())
    )
    assert loaded
    return loaded


def _relative_day(when: datetime | None) -> str:
    if when is None:
        return "—"
    local = as_ist(when)
    days = (ist_now().date() - local.date()).days
    if days == 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    return f"{days}d ago"


def _wh_inv(db: Session, warehouse_id: int, variant_id: int) -> WarehouseInventory:
    row = db.scalar(
        select(WarehouseInventory).where(
            WarehouseInventory.warehouse_id == warehouse_id,
            WarehouseInventory.variant_id == variant_id,
        )
    )
    if not row:
        row = WarehouseInventory(
            warehouse_id=warehouse_id,
            variant_id=variant_id,
            on_hand=0,
            reserved=0,
            reorder_point=0,
        )
        db.add(row)
        db.flush()
    return row


def _store_inv(db: Session, store_id: int, variant_id: int) -> StoreInventory:
    row = db.scalar(
        select(StoreInventory).where(
            StoreInventory.store_id == store_id,
            StoreInventory.variant_id == variant_id,
        )
    )
    if not row:
        row = StoreInventory(
            store_id=store_id,
            variant_id=variant_id,
            on_hand=0,
            on_floor=0,
            backroom=0,
            reserved=0,
            reorder_point=0,
        )
        db.add(row)
        db.flush()
    return row


def _take_store_stock(row: StoreInventory, qty: int, *, variant_id: int) -> None:
    available = int(row.on_hand or 0)
    if available < qty:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient store stock for variant {variant_id}",
        )
    remaining = qty
    backroom = int(row.backroom or 0)
    from_back = min(backroom, remaining)
    row.backroom = backroom - from_back
    remaining -= from_back
    if remaining:
        row.on_floor = max(0, int(row.on_floor or 0) - remaining)
    row.on_hand = int(row.on_floor or 0) + int(row.backroom or 0)


def apply_transfer_completion(db: Session, transfer: StockTransfer) -> None:
    """Move inventory for a completed transfer (same transaction as status flip)."""
    items = transfer.items or []
    if not items:
        raise HTTPException(status_code=400, detail="Transfer has no line items")

    validate_transfer_legs(
        from_warehouse_id=transfer.from_warehouse_id,
        from_store_id=transfer.from_store_id,
        to_warehouse_id=transfer.to_warehouse_id,
        to_store_id=transfer.to_store_id,
    )

    for item in items:
        if transfer.from_warehouse_id:
            src = _wh_inv(db, transfer.from_warehouse_id, item.variant_id)
            if int(src.on_hand or 0) < item.qty:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient warehouse stock for variant {item.variant_id}",
                )
            src.on_hand = int(src.on_hand) - item.qty
        else:
            assert transfer.from_store_id is not None
            src = _store_inv(db, transfer.from_store_id, item.variant_id)
            _take_store_stock(src, item.qty, variant_id=item.variant_id)

        if transfer.to_warehouse_id:
            dest = _wh_inv(db, transfer.to_warehouse_id, item.variant_id)
            dest.on_hand = int(dest.on_hand or 0) + item.qty
        else:
            assert transfer.to_store_id is not None
            dest = _store_inv(db, transfer.to_store_id, item.variant_id)
            dest.backroom = int(dest.backroom or 0) + item.qty
            dest.on_hand = int(dest.on_floor or 0) + int(dest.backroom or 0)


def reserve_allocation_stock(db: Session, warehouse_id: int, variant_id: int, qty: int) -> None:
    row = _wh_inv(db, warehouse_id, variant_id)
    available = int(row.on_hand or 0) - int(row.reserved or 0)
    if available < qty:
        raise HTTPException(status_code=400, detail="Insufficient available stock to reserve")
    row.reserved = int(row.reserved or 0) + qty
