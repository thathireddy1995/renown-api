"""Staff warehouse suppliers — /staff/warehouse/suppliers."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role
from app.dto.staff_dto import (
    StaffSupplierCreate,
    StaffSupplierListResponse,
    StaffSupplierOut,
    StaffSupplierUpdate,
)
from app.schemas import PurchaseOrder, Supplier, User

router = APIRouter(
    prefix="/staff/warehouse/suppliers", tags=["staff-warehouse-suppliers"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)

OPEN_PO_STATUSES = ("Open", "Pending", "Processing")


def _open_po_subq():
    return (
        select(
            PurchaseOrder.supplier_id.label("supplier_id"),
            func.count(PurchaseOrder.id).label("open_po"),
        )
        .where(PurchaseOrder.status.in_(OPEN_PO_STATUSES))
        .group_by(PurchaseOrder.supplier_id)
        .subquery()
    )


def _supplier_out(s: Supplier, open_po: int = 0) -> StaffSupplierOut:
    return StaffSupplierOut(
        id=s.code,
        name=s.name,
        contact=s.contact or "",
        category=s.category or "",
        leadTime=f"{s.lead_time_days} days",
        openPO=int(open_po or 0),
        status=s.status,
    )


@router.get("", response_model=StaffSupplierListResponse)
def list_suppliers(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffSupplierListResponse:
    limit, offset = page
    stats = _open_po_subq()
    stmt = select(Supplier, stats.c.open_po).outerjoin(
        stats, stats.c.supplier_id == Supplier.id
    )
    count_stmt = select(func.count()).select_from(Supplier)

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            Supplier.code.ilike(like),
            Supplier.name.ilike(like),
            Supplier.contact.ilike(like),
            Supplier.category.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(Supplier.id.asc()).limit(limit).offset(offset)
    ).all()
    return StaffSupplierListResponse(
        items=[_supplier_out(s, open_po) for s, open_po in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffSupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(
    body: StaffSupplierCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffSupplierOut:
    code = (body.code or "").strip()
    if not code:
        n = (db.scalar(select(func.count()).select_from(Supplier)) or 0) + 1
        code = f"SUP-{n:02d}"

    if db.scalar(select(Supplier.id).where(Supplier.code == code)):
        raise HTTPException(status_code=409, detail="Supplier code already exists")

    row = Supplier(
        code=code,
        name=body.name.strip(),
        contact=body.contact,
        category=body.category,
        lead_time_days=body.lead_time_days,
        status=body.status or "Active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _supplier_out(row)


@router.patch("/{supplier_ref}", response_model=StaffSupplierOut)
def update_supplier(
    supplier_ref: str,
    body: StaffSupplierUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffSupplierOut:
    row = db.scalar(select(Supplier).where(Supplier.code == supplier_ref))
    if not row and supplier_ref.isdigit():
        row = db.get(Supplier, int(supplier_ref))
    if not row:
        raise HTTPException(status_code=404, detail="Supplier not found")

    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)

    open_po = (
        db.scalar(
            select(func.count()).where(
                PurchaseOrder.supplier_id == row.id,
                PurchaseOrder.status.in_(OPEN_PO_STATUSES),
            )
        )
        or 0
    )
    return _supplier_out(row, open_po)


@router.delete("/{supplier_ref}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(
    supplier_ref: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> None:
    row = db.scalar(select(Supplier).where(Supplier.code == supplier_ref))
    if not row and supplier_ref.isdigit():
        row = db.get(Supplier, int(supplier_ref))
    if not row:
        raise HTTPException(status_code=404, detail="Supplier not found")
    db.delete(row)
    db.commit()
