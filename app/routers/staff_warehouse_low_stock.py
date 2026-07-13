"""Staff warehouse low-stock alerts — single aggregate query."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import TokenPrincipal, require_role
from app.database import get_db
from app.deps import pagination
from app.dto.operations_dto import LowStockListResponse, LowStockOut
from app.schemas import Product, ProductVariant, Supplier, Warehouse, WarehouseInventory

router = APIRouter(
    prefix="/staff/warehouse/low-stock",
    tags=["staff-warehouse-low-stock"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


def _wh_id(db: Session, principal: TokenPrincipal) -> int | None:
    if principal.warehouse_id is not None:
        return principal.warehouse_id
    wh = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
    return wh.id if wh else None


@router.get("", response_model=LowStockListResponse)
def list_low_stock(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> LowStockListResponse:
    limit, offset = page
    wid = _wh_id(db, principal)

    supplier_name = (
        select(Supplier.name)
        .where(Supplier.status == "Active")
        .order_by(Supplier.id.asc())
        .limit(1)
        .scalar_subquery()
    )

    suggested = case(
        (
            WarehouseInventory.on_hand <= 0,
            WarehouseInventory.reorder_point * 2 + 100,
        ),
        else_=func.greatest(
            WarehouseInventory.reorder_point * 2 - WarehouseInventory.on_hand,
            WarehouseInventory.reorder_point,
        ),
    )
    status_expr = case(
        (WarehouseInventory.on_hand <= 0, "Out of Stock"),
        else_="Low",
    )

    stmt = (
        select(
            WarehouseInventory.id,
            ProductVariant.sku,
            Product.name,
            WarehouseInventory.on_hand,
            WarehouseInventory.reorder_point,
            suggested.label("suggested"),
            func.coalesce(supplier_name, "—").label("supplier"),
            status_expr.label("status"),
        )
        .join(ProductVariant, ProductVariant.id == WarehouseInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(WarehouseInventory.on_hand <= WarehouseInventory.reorder_point)
    )
    count_stmt = (
        select(func.count())
        .select_from(WarehouseInventory)
        .where(WarehouseInventory.on_hand <= WarehouseInventory.reorder_point)
    )
    if wid is not None:
        stmt = stmt.where(WarehouseInventory.warehouse_id == wid)
        count_stmt = count_stmt.where(WarehouseInventory.warehouse_id == wid)
    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(ProductVariant.sku.ilike(q), Product.name.ilike(q))
        )
        count_stmt = (
            count_stmt.join(
                ProductVariant, ProductVariant.id == WarehouseInventory.variant_id
            )
            .join(Product, Product.id == ProductVariant.product_id)
            .where(or_(ProductVariant.sku.ilike(q), Product.name.ilike(q)))
        )

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(WarehouseInventory.on_hand.asc()).limit(limit).offset(offset)
    ).all()

    items = [
        LowStockOut(
            id=str(r[0]),
            sku=r[1] or "",
            product=r[2] or "",
            onHand=int(r[3] or 0),
            reorder=int(r[4] or 0),
            suggested=int(r[5] or 0),
            supplier=r[6] or "—",
            status=r[7] or "Low",
        )
        for r in rows
    ]
    return LowStockListResponse(items=items, total=total, limit=limit, offset=offset)
