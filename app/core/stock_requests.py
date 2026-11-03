"""Stock requests (store or warehouse asking a warehouse for stock) and their lines."""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.ist import now as ist_now
from app.core.stock_transfers import next_transfer_number
from app.schemas import (
    Product,
    ProductVariant,
    StockTransfer,
    StockTransferItem,
    Store,
    TransferRequest,
    TransferRequestItem,
    Warehouse,
    WarehouseInventory,
)

URGENCIES = ("Low", "Medium", "High")


@dataclass
class RequestLine:
    variant: ProductVariant
    qty: int


def request_eager_options():
    return (
        selectinload(TransferRequest.requester_warehouse),
        selectinload(TransferRequest.target_warehouse),
        selectinload(TransferRequest.store),
        selectinload(TransferRequest.variant)
        .selectinload(ProductVariant.product)
        .selectinload(Product.images),
        selectinload(TransferRequest.items)
        .selectinload(TransferRequestItem.variant)
        .selectinload(ProductVariant.product)
        .selectinload(Product.images),
        selectinload(TransferRequest.stock_transfer),
    )


def variant_image(variant: ProductVariant) -> str | None:
    if variant.images:
        return variant.images[0]
    product_images = sorted(
        (variant.product.images if variant.product else None) or [],
        key=lambda img: (img.sort_order, img.id),
    )
    return product_images[0].url if product_images else None


def variant_label(value: str | None) -> str:
    return "" if value == "__deleted__" else (value or "")


def request_lines(req: TransferRequest) -> list[RequestLine]:
    """Lines of a request; requests created before line items count as one line."""
    if req.items:
        return [RequestLine(item.variant, int(item.qty)) for item in req.items]
    if req.variant is None:
        return []
    return [RequestLine(req.variant, int(req.qty_requested or 0))]


def normalize_urgency(value: str | None) -> str:
    urgency = (value or "Medium").strip().title()
    return urgency if urgency in URGENCIES else "Medium"


def next_request_number(db: Session) -> str:
    base = int(ist_now().timestamp() * 1000) % 10_000_000
    for step in range(25):
        num = f"REQ-{base + step}"
        if not db.scalar(select(TransferRequest.id).where(TransferRequest.request_number == num)):
            return num
    raise HTTPException(status_code=500, detail="Could not allocate request number")


def store_source_warehouse(db: Session, store: Store) -> Warehouse | None:
    if store.warehouse_id:
        warehouse = db.get(Warehouse, store.warehouse_id)
        if warehouse:
            return warehouse
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def warehouse_available(db: Session, warehouse_id: int, variant_ids: list[int]) -> dict[int, int]:
    if not variant_ids:
        return {}
    rows = db.execute(
        select(
            WarehouseInventory.variant_id,
            func.sum(WarehouseInventory.on_hand - WarehouseInventory.reserved),
        )
        .where(
            WarehouseInventory.warehouse_id == warehouse_id,
            WarehouseInventory.variant_id.in_(variant_ids),
        )
        .group_by(WarehouseInventory.variant_id)
    ).all()
    return {int(vid): max(0, int(avail or 0)) for vid, avail in rows}


def create_store_request(
    db: Session,
    *,
    store: Store,
    warehouse: Warehouse,
    lines: list[tuple[int, int]],
    urgency: str,
) -> TransferRequest:
    """Validate lines against warehouse availability and add one pending request (no commit)."""
    merged: dict[int, int] = {}
    for variant_id, qty in lines:
        if qty < 1:
            raise HTTPException(status_code=422, detail="Quantity must be at least 1")
        merged[variant_id] = merged.get(variant_id, 0) + qty
    if not merged:
        raise HTTPException(status_code=422, detail="Add at least one item to the request")

    variants = {
        v.id: v
        for v in db.scalars(select(ProductVariant).where(ProductVariant.id.in_(merged)))
    }
    missing = [vid for vid in merged if vid not in variants]
    if missing:
        raise HTTPException(status_code=404, detail=f"Variant {missing[0]} not found")

    available = warehouse_available(db, warehouse.id, list(merged))
    for vid, qty in merged.items():
        if qty > available.get(vid, 0):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{variants[vid].sku}: only {available.get(vid, 0)} available "
                    f"in {warehouse.name}"
                ),
            )

    first_id = next(iter(merged))
    req = TransferRequest(
        request_number=next_request_number(db),
        store_id=store.id,
        target_warehouse_id=warehouse.id,
        variant_id=first_id,
        qty_requested=sum(merged.values()),
        urgency=normalize_urgency(urgency),
        status="pending",
    )
    req.items = [TransferRequestItem(variant_id=vid, qty=qty) for vid, qty in merged.items()]
    db.add(req)
    return req


def approve_request(db: Session, req: TransferRequest) -> StockTransfer:
    """Turn a pending request into one stock transfer holding every line (no commit)."""
    if (req.status or "").lower() != "pending":
        raise HTTPException(status_code=422, detail="Only pending requests can be approved")
    if not req.target_warehouse_id:
        raise HTTPException(status_code=422, detail="Request has no source warehouse")
    if not req.store_id and not req.requester_warehouse_id:
        raise HTTPException(status_code=422, detail="Request has no destination")
    lines = request_lines(req)
    if not lines:
        raise HTTPException(status_code=422, detail="Request has no items")

    transfer = StockTransfer(
        transfer_number=next_transfer_number(db),
        from_warehouse_id=req.target_warehouse_id,
        to_warehouse_id=None if req.store_id else req.requester_warehouse_id,
        to_store_id=req.store_id,
        status="approved",
        requested_by=req.request_number,
    )
    transfer.items = [StockTransferItem(variant_id=line.variant.id, qty=line.qty) for line in lines]
    db.add(transfer)
    db.flush()
    req.status = "approved"
    req.stock_transfer_id = transfer.id
    return transfer
