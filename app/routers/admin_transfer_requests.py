"""Admin transfer requests — /admin/transfer-requests."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminTransferRequestListResponse,
    AdminTransferRequestOut,
)
from app.schemas import (
    ProductVariant,
    StockTransfer,
    StockTransferItem,
    TransferRequest,
    Warehouse,
)

router = APIRouter(prefix="/admin/transfer-requests", tags=["admin-transfer-requests"], dependencies=[Depends(require_role("admin"))])

STATUS_LABEL = {
    "pending": "Pending",
    "approved": "Approved",
    "rejected": "Rejected",
}


def _req_out(r: TransferRequest) -> AdminTransferRequestOut:
    return AdminTransferRequestOut(
        id=r.request_number,
        requester=r.requester_warehouse.name if r.requester_warehouse else (
            r.store.name if r.store else ""
        ),
        target=r.target_warehouse.name if r.target_warehouse else "",
        sku=r.variant.sku if r.variant else "",
        qty=r.qty_requested,
        urgency=r.urgency or "Medium",
        date=r.created_at.strftime("%Y-%m-%d") if r.created_at else "",
        status=STATUS_LABEL.get((r.status or "").lower(), r.status.title()),
    )


def _load_options():
    return (
        selectinload(TransferRequest.requester_warehouse),
        selectinload(TransferRequest.target_warehouse),
        selectinload(TransferRequest.store),
        selectinload(TransferRequest.variant),
    )


@router.get("", response_model=AdminTransferRequestListResponse)
def list_transfer_requests(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> AdminTransferRequestListResponse:
    limit, offset = page
    stmt = select(TransferRequest).options(*_load_options())
    count_stmt = select(func.count()).select_from(TransferRequest)

    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = (
            stmt.outerjoin(Warehouse, Warehouse.id == TransferRequest.requester_warehouse_id)
            .outerjoin(ProductVariant, ProductVariant.id == TransferRequest.variant_id)
        )
        count_stmt = (
            count_stmt.outerjoin(
                Warehouse, Warehouse.id == TransferRequest.requester_warehouse_id
            ).outerjoin(ProductVariant, ProductVariant.id == TransferRequest.variant_id)
        )
        filt = or_(
            TransferRequest.request_number.ilike(like),
            Warehouse.name.ilike(like),
            ProductVariant.sku.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(TransferRequest.id.desc()).limit(limit).offset(offset)
    ).all()
    return AdminTransferRequestListResponse(
        items=[_req_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _resolve(db: Session, ref: str) -> TransferRequest | None:
    stmt = select(TransferRequest).options(*_load_options())
    row = db.scalar(stmt.where(TransferRequest.request_number == ref))
    if row:
        return row
    if ref.isdigit():
        return db.scalar(stmt.where(TransferRequest.id == int(ref)))
    return None


@router.patch("/{request_ref}/approve", response_model=AdminTransferRequestOut)
def approve_transfer_request(
    request_ref: str, db: Session = Depends(get_db)
) -> AdminTransferRequestOut:
    req = _resolve(db, request_ref)
    if not req:
        raise HTTPException(status_code=404, detail="Transfer request not found")
    if (req.status or "").lower() != "pending":
        raise HTTPException(status_code=422, detail="Only pending requests can be approved")
    if not req.target_warehouse_id or not req.requester_warehouse_id:
        raise HTTPException(
            status_code=422, detail="Request needs requester and target warehouses"
        )

    # Create stock transfer: stock moves from target (supplier) → requester
    num = f"TR-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(StockTransfer.id).where(StockTransfer.transfer_number == num)):
        num = f"TR-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    transfer = StockTransfer(
        transfer_number=num,
        from_warehouse_id=req.target_warehouse_id,
        to_warehouse_id=req.requester_warehouse_id,
        to_store_id=req.store_id,
        status="approved",
        requested_by=req.request_number,
    )
    db.add(transfer)
    db.flush()
    db.add(
        StockTransferItem(
            stock_transfer_id=transfer.id,
            variant_id=req.variant_id,
            qty=req.qty_requested,
        )
    )
    req.status = "approved"
    req.stock_transfer_id = transfer.id
    db.commit()

    refreshed = _resolve(db, request_ref)
    assert refreshed
    return _req_out(refreshed)


@router.patch("/{request_ref}/reject", response_model=AdminTransferRequestOut)
def reject_transfer_request(
    request_ref: str, db: Session = Depends(get_db)
) -> AdminTransferRequestOut:
    req = _resolve(db, request_ref)
    if not req:
        raise HTTPException(status_code=404, detail="Transfer request not found")
    if (req.status or "").lower() != "pending":
        raise HTTPException(status_code=422, detail="Only pending requests can be rejected")
    req.status = "rejected"
    db.commit()
    refreshed = _resolve(db, request_ref)
    assert refreshed
    return _req_out(refreshed)
