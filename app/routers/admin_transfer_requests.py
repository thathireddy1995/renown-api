"""Admin transfer requests — /admin/transfer-requests."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.ist import format_ist_date
from app.core.stock_requests import (
    RequestLine,
    approve_request,
    next_request_number,
    request_eager_options,
    request_lines,
    variant_image,
    variant_label,
)
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminTransferRequestCreate,
    AdminTransferRequestLineOut,
    AdminTransferRequestListResponse,
    AdminTransferRequestOut,
)
from app.schemas import (
    ProductVariant,
    Store,
    TransferRequest,
    TransferRequestItem,
    Warehouse,
)

router = APIRouter(prefix="/admin/transfer-requests", tags=["admin-transfer-requests"], dependencies=[Depends(require_role("admin"))])

STATUS_LABEL = {
    "pending": "Pending",
    "approved": "Approved",
    "rejected": "Rejected",
}


def _req_out(r: TransferRequest) -> AdminTransferRequestOut:
    lines = request_lines(r)
    return AdminTransferRequestOut(
        id=r.request_number,
        requester=r.requester_warehouse.name if r.requester_warehouse else (
            r.store.name if r.store else ""
        ),
        target=r.target_warehouse.name if r.target_warehouse else "",
        sku=lines[0].variant.sku if lines else "",
        qty=sum(line.qty for line in lines) if lines else r.qty_requested,
        urgency=r.urgency or "Medium",
        date=format_ist_date(r.created_at),
        status=STATUS_LABEL.get((r.status or "").lower(), r.status.title()),
        requester_type="store" if r.store_id and not r.requester_warehouse_id else "warehouse",
        lines=[_line_out(line) for line in lines],
        transfer=r.stock_transfer.transfer_number if r.stock_transfer else None,
    )


def _line_out(line: RequestLine) -> AdminTransferRequestLineOut:
    v = line.variant
    return AdminTransferRequestLineOut(
        variant_id=v.id,
        sku=v.sku,
        name=v.product.name if v.product else v.sku,
        color=variant_label(v.color),
        size=variant_label(v.size),
        image=variant_image(v),
        qty=line.qty,
    )


def _load_options():
    return request_eager_options()


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
            .outerjoin(Store, Store.id == TransferRequest.store_id)
            .outerjoin(ProductVariant, ProductVariant.id == TransferRequest.variant_id)
        )
        count_stmt = (
            count_stmt.outerjoin(
                Warehouse, Warehouse.id == TransferRequest.requester_warehouse_id
            )
            .outerjoin(Store, Store.id == TransferRequest.store_id)
            .outerjoin(ProductVariant, ProductVariant.id == TransferRequest.variant_id)
        )
        item_variant = aliased(ProductVariant)
        item_sku = (
            select(TransferRequestItem.id)
            .join(item_variant, item_variant.id == TransferRequestItem.variant_id)
            .where(
                TransferRequestItem.transfer_request_id == TransferRequest.id,
                item_variant.sku.ilike(like),
            )
            .exists()
        )
        filt = or_(
            TransferRequest.request_number.ilike(like),
            Warehouse.name.ilike(like),
            Store.name.ilike(like),
            ProductVariant.sku.ilike(like),
            item_sku,
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


@router.post("", response_model=AdminTransferRequestOut, status_code=status.HTTP_201_CREATED)
def create_transfer_request(
    body: AdminTransferRequestCreate, db: Session = Depends(get_db)
) -> AdminTransferRequestOut:
    if body.requester_warehouse_id == body.target_warehouse_id:
        raise HTTPException(status_code=422, detail="Requester and target must differ")
    if body.qty < 1:
        raise HTTPException(status_code=422, detail="Quantity must be at least 1")
    if body.qty > 10000:
        raise HTTPException(status_code=422, detail="Quantity cannot exceed 10000")
    if not db.get(Warehouse, body.requester_warehouse_id):
        raise HTTPException(status_code=404, detail="Requester warehouse not found")
    if not db.get(Warehouse, body.target_warehouse_id):
        raise HTTPException(status_code=404, detail="Target warehouse not found")
    if not db.get(ProductVariant, body.variant_id):
        raise HTTPException(status_code=404, detail="Variant not found")

    urgency = (body.urgency or "Medium").strip().title()
    if urgency not in ("Low", "Medium", "High"):
        raise HTTPException(status_code=422, detail="Urgency must be Low, Medium, or High")

    num = next_request_number(db)
    row = TransferRequest(
        request_number=num,
        requester_warehouse_id=body.requester_warehouse_id,
        target_warehouse_id=body.target_warehouse_id,
        variant_id=body.variant_id,
        qty_requested=body.qty,
        urgency=urgency,
        status="pending",
    )
    row.items = [TransferRequestItem(variant_id=body.variant_id, qty=body.qty)]
    db.add(row)
    db.commit()

    loaded = _resolve(db, num)
    assert loaded
    return _req_out(loaded)


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
    approve_request(db, req)
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
