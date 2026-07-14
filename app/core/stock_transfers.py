"""Shared stock-transfer query helpers + inventory moves (Phase 9)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

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
        selectinload(StockTransfer.to_warehouse),
        selectinload(StockTransfer.to_store),
    )


def list_stock_transfers_query(
    *,
    status: str | None = None,
    search: str | None = None,
    from_warehouse_id: int | None = None,
):
    stmt = select(StockTransfer).options(*transfer_eager_options())
    count_stmt = select(func.count()).select_from(StockTransfer)

    if from_warehouse_id is not None:
        filt = or_(
            StockTransfer.from_warehouse_id == from_warehouse_id,
            StockTransfer.to_warehouse_id == from_warehouse_id,
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    if status and status.lower() not in ("all", ""):
        db_status = normalize_transfer_status(status)
        stmt = stmt.where(StockTransfer.status == db_status)
        count_stmt = count_stmt.where(StockTransfer.status == db_status)

    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = (
            stmt.join(Warehouse, Warehouse.id == StockTransfer.from_warehouse_id)
            .outerjoin(
                StockTransferItem,
                StockTransferItem.stock_transfer_id == StockTransfer.id,
            )
            .outerjoin(ProductVariant, ProductVariant.id == StockTransferItem.variant_id)
        )
        count_stmt = (
            count_stmt.join(Warehouse, Warehouse.id == StockTransfer.from_warehouse_id)
            .outerjoin(
                StockTransferItem,
                StockTransferItem.stock_transfer_id == StockTransfer.id,
            )
            .outerjoin(ProductVariant, ProductVariant.id == StockTransferItem.variant_id)
        )
        filt = or_(
            StockTransfer.transfer_number.ilike(like),
            Warehouse.name.ilike(like),
            ProductVariant.sku.ilike(like),
        )
        stmt = stmt.where(filt).distinct()
        count_stmt = count_stmt.where(filt)

    return stmt, count_stmt


def admin_transfer_row(t: StockTransfer) -> dict:
    item = (t.items or [None])[0]
    sku = item.variant.sku if item and item.variant else ""
    qty = item.qty if item else 0
    to_name = (
        t.to_warehouse.name
        if t.to_warehouse
        else (t.to_store.name if t.to_store else "")
    )
    return {
        "id": t.transfer_number,
        "from": t.from_warehouse.name if t.from_warehouse else "",
        "to": to_name,
        "sku": sku,
        "qty": qty,
        "status": admin_status_label(t.status),
        "eta": t.eta.isoformat() if t.eta else "—",
        "created": t.created_at.strftime("%Y-%m-%d") if t.created_at else "",
    }


def staff_transfer_row(
    t: StockTransfer,
    *,
    items_override: int | None = None,
    qty_override: int | None = None,
) -> dict:
    items = t.items or []
    qty = sum(i.qty for i in items)
    to_name = (
        t.to_warehouse.name
        if t.to_warehouse
        else (t.to_store.name if t.to_store else "")
    )
    return {
        "id": t.transfer_number,
        "from": t.from_warehouse.name if t.from_warehouse else "",
        "to": to_name,
        "items": items_override if items_override is not None else len(items),
        "qty": qty_override if qty_override is not None else qty,
        "requested": _relative_day(t.created_at),
        "status": staff_status_label(t.status),
    }


def _relative_day(when: datetime | None) -> str:
    if when is None:
        return "—"
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    days = (now.date() - when.date()).days
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


def apply_transfer_completion(db: Session, transfer: StockTransfer) -> None:
    """Move inventory for a completed transfer (same transaction as status flip)."""
    for item in transfer.items or []:
        src = _wh_inv(db, transfer.from_warehouse_id, item.variant_id)
        if int(src.on_hand or 0) < item.qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for variant {item.variant_id}",
            )
        src.on_hand = int(src.on_hand) - item.qty

        if transfer.to_warehouse_id:
            dest = _wh_inv(db, transfer.to_warehouse_id, item.variant_id)
            dest.on_hand = int(dest.on_hand or 0) + item.qty
        elif transfer.to_store_id:
            dest = _store_inv(db, transfer.to_store_id, item.variant_id)
            dest.backroom = int(dest.backroom or 0) + item.qty
            dest.on_hand = int(dest.on_floor or 0) + int(dest.backroom or 0)
        else:
            raise HTTPException(
                status_code=400, detail="Transfer has no destination warehouse or store"
            )


def reserve_allocation_stock(db: Session, warehouse_id: int, variant_id: int, qty: int) -> None:
    row = _wh_inv(db, warehouse_id, variant_id)
    available = int(row.on_hand or 0) - int(row.reserved or 0)
    if available < qty:
        raise HTTPException(status_code=400, detail="Insufficient available stock to reserve")
    row.reserved = int(row.reserved or 0) + qty
