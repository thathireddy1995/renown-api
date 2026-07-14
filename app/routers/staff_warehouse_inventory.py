"""Staff warehouse inventory — /staff/warehouse/inventory."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.inventory_status import warehouse_stock_status
from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role, TokenPrincipal
from app.routers.admin_warehouses import case_dot_color
from app.schemas import Category, Product, ProductVariant, User, Warehouse, WarehouseInventory

router = APIRouter(
    prefix="/staff/warehouse/inventory",
    tags=["staff-warehouse-inventory"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


class StaffWhInventoryOut(BaseModel):
    id: str
    sku: str
    product: str
    category: str
    zone: str
    onHand: int
    reserved: int
    available: int
    status: str
    variant_id: int = 0


class StaffWhInventoryListResponse(BaseModel):
    items: list[StaffWhInventoryOut]
    total: int
    limit: int
    offset: int
    warehouse_id: int | None = None
    warehouse_name: str = ""


class StaffWhStockAdjust(BaseModel):
    sku: str | None = None
    variant_id: int | None = None
    on_hand: int | None = Field(default=None, ge=0)
    delta: int | None = None
    reason: str | None = None
    warehouse_id: int | None = None


def _default_warehouse(db: Session) -> Warehouse | None:
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def _resolve_warehouse(
    db: Session, principal: TokenPrincipal, warehouse_id: int | None
) -> Warehouse | None:
    wid = principal.warehouse_id or warehouse_id
    if wid is not None:
        return db.get(Warehouse, wid)
    return _default_warehouse(db)


def _staff_status(on_hand: int, reserved: int, health: str) -> str:
    available = max(0, on_hand - reserved)
    if on_hand <= 0 or available <= 0:
        return "Out of Stock"
    if health in ("Critical", "Low"):
        return "Low"
    return "In Stock"


def _row_out(inv: WarehouseInventory, sku: str, product: str, category: str, health: str) -> StaffWhInventoryOut:
    on_hand = int(inv.on_hand or 0)
    reserved = int(inv.reserved or 0)
    return StaffWhInventoryOut(
        id=f"inv-{inv.id}",
        sku=sku or "",
        product=product or sku or "",
        category=category or "General",
        zone=inv.bin_location or "—",
        onHand=on_hand,
        reserved=reserved,
        available=max(0, on_hand - reserved),
        status=_staff_status(on_hand, reserved, str(health or "Healthy")),
        variant_id=int(inv.variant_id),
    )


@router.get("", response_model=StaffWhInventoryListResponse)
def list_inventory(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    warehouse_id: int | None = None,
    search: str | None = Query(None, alias="q"),
) -> StaffWhInventoryListResponse:
    limit, offset = page
    warehouse = _resolve_warehouse(db, principal, warehouse_id)
    if not warehouse:
        return StaffWhInventoryListResponse(items=[], total=0, limit=limit, offset=offset)

    health_col = warehouse_stock_status(
        WarehouseInventory.on_hand, WarehouseInventory.reorder_point
    ).label("health")
    product_label = func.concat(Product.name, case_dot_color()).label("product_label")
    cat_expr = func.coalesce(Category.name, "General")

    stmt = (
        select(
            WarehouseInventory,
            ProductVariant.sku,
            product_label,
            cat_expr,
            health_col,
        )
        .join(ProductVariant, ProductVariant.id == WarehouseInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(WarehouseInventory.warehouse_id == warehouse.id)
    )
    count_stmt = (
        select(func.count())
        .select_from(WarehouseInventory)
        .join(ProductVariant, ProductVariant.id == WarehouseInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(WarehouseInventory.warehouse_id == warehouse.id)
    )

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(ProductVariant.sku.ilike(like), Product.name.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(WarehouseInventory.id.asc()).limit(limit).offset(offset)
    ).all()

    items = [
        _row_out(inv, sku or "", product or "", category or "General", str(health or "Healthy"))
        for inv, sku, product, category, health in rows
    ]
    return StaffWhInventoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        warehouse_id=warehouse.id,
        warehouse_name=warehouse.name or "",
    )


@router.post("/adjust", response_model=StaffWhInventoryOut, status_code=status.HTTP_200_OK)
def adjust_stock(
    body: StaffWhStockAdjust,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffWhInventoryOut:
    warehouse = _resolve_warehouse(db, principal, body.warehouse_id)
    if not warehouse:
        raise HTTPException(status_code=400, detail="No warehouse configured")

    inv: WarehouseInventory | None = None
    if body.variant_id is not None:
        inv = db.scalar(
            select(WarehouseInventory).where(
                WarehouseInventory.warehouse_id == warehouse.id,
                WarehouseInventory.variant_id == body.variant_id,
            )
        )
    if inv is None and body.sku:
        variant = db.scalar(
            select(ProductVariant).where(ProductVariant.sku.ilike(body.sku.strip()))
        )
        if not variant:
            raise HTTPException(status_code=404, detail="SKU not found")
        inv = db.scalar(
            select(WarehouseInventory).where(
                WarehouseInventory.warehouse_id == warehouse.id,
                WarehouseInventory.variant_id == variant.id,
            )
        )
        if inv is None:
            inv = WarehouseInventory(
                warehouse_id=warehouse.id,
                variant_id=variant.id,
                on_hand=0,
                reserved=0,
                reorder_point=0,
                bin_location=None,
            )
            db.add(inv)
            db.flush()

    if inv is None:
        raise HTTPException(status_code=404, detail="Inventory row not found")

    if body.on_hand is not None:
        inv.on_hand = body.on_hand
    elif body.delta is not None:
        inv.on_hand = max(0, int(inv.on_hand or 0) + body.delta)
    else:
        raise HTTPException(status_code=422, detail="Provide on_hand or delta")

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    variant = db.get(ProductVariant, inv.variant_id)
    product = db.get(Product, variant.product_id) if variant else None
    category = None
    if product and product.category_id:
        cat = db.get(Category, product.category_id)
        category = cat.name if cat else None
    health = "Healthy"
    on_hand = int(inv.on_hand or 0)
    reorder = int(inv.reorder_point or 0)
    if on_hand <= 0 or (reorder and on_hand < reorder * 0.5):
        health = "Critical"
    elif reorder and on_hand < reorder:
        health = "Low"

    return _row_out(
        inv,
        variant.sku if variant else "",
        product.name if product else "",
        category or "General",
        health,
    )
