"""Admin stock allocation — /admin/stock-allocation."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.stock_transfers import reserve_allocation_stock
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminStockAllocationListResponse,
    AdminStockAllocationOut,
)
from app.schemas import ProductVariant, StockAllocation, Warehouse

router = APIRouter(prefix="/admin/stock-allocation", tags=["admin-stock-allocation"], dependencies=[Depends(require_role("admin"))])

# UI display statuses (seed stores these); DB also accepts pending/allocated/released.
DISPLAY = {
    "pending": "Allocated",
    "allocated": "Allocated",
    "released": "Ready to ship",
}


def _label(raw: str) -> str:
    key = (raw or "").lower()
    if raw in (
        "Allocated",
        "Picking",
        "Packed",
        "Ready to ship",
        "Backorder",
    ):
        return raw
    return DISPLAY.get(key, raw or "Allocated")


def _alloc_out(a: StockAllocation) -> AdminStockAllocationOut:
    return AdminStockAllocationOut(
        id=a.allocation_number,
        order=a.order_number or (a.order.order_number if a.order else ""),
        sku=a.variant.sku if a.variant else "",
        qty=a.qty,
        warehouse=a.warehouse.name if a.warehouse else "",
        picker=a.picker_name or "—",
        created=a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
        status=_label(a.status),
    )


@router.get("", response_model=AdminStockAllocationListResponse)
def list_allocations(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> AdminStockAllocationListResponse:
    limit, offset = page
    stmt = select(StockAllocation).options(
        selectinload(StockAllocation.variant),
        selectinload(StockAllocation.warehouse),
        selectinload(StockAllocation.order),
    )
    count_stmt = select(func.count()).select_from(StockAllocation)

    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = (
            stmt.join(ProductVariant, ProductVariant.id == StockAllocation.variant_id)
            .join(Warehouse, Warehouse.id == StockAllocation.warehouse_id)
        )
        count_stmt = (
            count_stmt.join(
                ProductVariant, ProductVariant.id == StockAllocation.variant_id
            ).join(Warehouse, Warehouse.id == StockAllocation.warehouse_id)
        )
        filt = or_(
            StockAllocation.allocation_number.ilike(like),
            StockAllocation.order_number.ilike(like),
            ProductVariant.sku.ilike(like),
            Warehouse.name.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(StockAllocation.id.desc()).limit(limit).offset(offset)
    ).all()

    # Stat card counts from all rows (single GROUP BY)
    status_counts = dict(
        db.execute(
            select(StockAllocation.status, func.count()).group_by(StockAllocation.status)
        ).all()
    )
    counts = {
        "Allocated": 0,
        "In picking": 0,
        "Ready": 0,
        "Backorder": 0,
    }
    for raw, n in status_counts.items():
        label = _label(raw)
        if label == "Allocated":
            counts["Allocated"] += int(n)
        elif label == "Picking":
            counts["In picking"] += int(n)
        elif label in ("Ready to ship", "Packed"):
            counts["Ready"] += int(n)
        elif label == "Backorder":
            counts["Backorder"] += int(n)

    return AdminStockAllocationListResponse(
        items=[_alloc_out(a) for a in rows],
        total=total,
        limit=limit,
        offset=offset,
        counts=counts,
    )


def _resolve(db: Session, ref: str) -> StockAllocation | None:
    stmt = select(StockAllocation).options(
        selectinload(StockAllocation.variant),
        selectinload(StockAllocation.warehouse),
        selectinload(StockAllocation.order),
    )
    row = db.scalar(stmt.where(StockAllocation.allocation_number == ref))
    if row:
        return row
    if ref.isdigit():
        return db.scalar(stmt.where(StockAllocation.id == int(ref)))
    return None


@router.post("/{allocation_ref}/allocate", response_model=AdminStockAllocationOut)
def allocate_stock(
    allocation_ref: str, db: Session = Depends(get_db)
) -> AdminStockAllocationOut:
    alloc = _resolve(db, allocation_ref)
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found")

    current = (alloc.status or "").lower()
    if current in ("allocated",) or alloc.status == "Allocated":
        raise HTTPException(status_code=422, detail="Already allocated")
    if current not in ("pending", "backorder") and alloc.status not in (
        "pending",
        "Backorder",
    ):
        raise HTTPException(
            status_code=422, detail="Allocation cannot be reserved in this state"
        )

    reserve_allocation_stock(db, alloc.warehouse_id, alloc.variant_id, alloc.qty)
    alloc.status = "Allocated"
    db.commit()
    refreshed = _resolve(db, allocation_ref)
    assert refreshed
    return _alloc_out(refreshed)
