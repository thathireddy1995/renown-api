"""Staff warehouse — linked stores and their inventory (JWT warehouse scoped)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.inventory_status import store_stock_status
from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role, TokenPrincipal
from app.routers.admin_warehouses import case_dot_color
from app.schemas import Category, Product, ProductVariant, Store, StoreInventory, User, Warehouse

router = APIRouter(
    prefix="/staff/warehouse/stores",
    tags=["staff-warehouse-stores"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


class WhStoreOut(BaseModel):
    id: int
    code: str
    name: str
    city: str = ""
    status: str = ""
    skus: int = 0
    label: str = ""


class WhStoreListResponse(BaseModel):
    items: list[WhStoreOut]
    total: int
    warehouse_id: int | None = None
    warehouse_name: str = ""


class WhStoreInventoryOut(BaseModel):
    id: str
    sku: str
    product: str
    category: str
    qty: int
    onFloor: int = 0
    backroom: int = 0
    reserved: int = 0
    reorder: int = 0
    bin: str = ""
    status: str
    variant_id: int = 0


class WhStoreInventoryListResponse(BaseModel):
    items: list[WhStoreInventoryOut]
    total: int
    limit: int
    offset: int
    store_id: int
    store_name: str = ""
    store_code: str = ""


def _resolve_warehouse(db: Session, principal: TokenPrincipal) -> Warehouse | None:
    if principal.warehouse_id is not None:
        return db.get(Warehouse, principal.warehouse_id)
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def _owned_store(db: Session, warehouse: Warehouse, store_id: int) -> Store:
    store = db.get(Store, store_id)
    if not store or store.warehouse_id != warehouse.id:
        raise HTTPException(status_code=404, detail="Store not found for this warehouse")
    return store


def _staff_status(qty: int, health: str) -> str:
    if qty <= 0 or health == "Critical":
        return "Out of Stock" if qty <= 0 else "Low"
    if health == "Low":
        return "Low"
    return "In Stock"


@router.get("", response_model=WhStoreListResponse)
def list_warehouse_stores(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
) -> WhStoreListResponse:
    """Stores linked to the manager's warehouse only."""
    warehouse = _resolve_warehouse(db, principal)
    if not warehouse:
        return WhStoreListResponse(items=[], total=0)

    sku_counts = dict(
        db.execute(
            select(StoreInventory.store_id, func.count(StoreInventory.id))
            .join(Store, Store.id == StoreInventory.store_id)
            .where(Store.warehouse_id == warehouse.id)
            .group_by(StoreInventory.store_id)
        ).all()
    )

    rows = db.scalars(
        select(Store)
        .where(Store.warehouse_id == warehouse.id)
        .order_by(Store.name.asc())
    ).all()

    items = [
        WhStoreOut(
            id=s.id,
            code=s.code or "",
            name=s.name or "",
            city=s.city or "",
            status=s.status or "",
            skus=int(sku_counts.get(s.id, 0)),
            label=f"{s.name} · {s.code}" if s.code else (s.name or ""),
        )
        for s in rows
    ]
    return WhStoreListResponse(
        items=items,
        total=len(items),
        warehouse_id=warehouse.id,
        warehouse_name=warehouse.name or "",
    )


@router.get("/{store_id}/inventory", response_model=WhStoreInventoryListResponse)
def list_store_inventory_for_warehouse(
    store_id: int,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> WhStoreInventoryListResponse:
    warehouse = _resolve_warehouse(db, principal)
    if not warehouse:
        raise HTTPException(status_code=400, detail="No warehouse configured")
    store = _owned_store(db, warehouse, store_id)

    limit, offset = page
    total_qty = StoreInventory.on_floor + StoreInventory.backroom
    health_col = store_stock_status(total_qty, StoreInventory.reorder_point).label("health")
    product_label = func.concat(Product.name, case_dot_color()).label("product_label")
    cat_expr = func.coalesce(Category.name, "General")

    stmt = (
        select(
            StoreInventory,
            ProductVariant.sku,
            product_label,
            cat_expr,
            health_col,
            ProductVariant.id,
        )
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(StoreInventory.store_id == store.id)
    )
    count_stmt = (
        select(func.count())
        .select_from(StoreInventory)
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(StoreInventory.store_id == store.id)
    )
    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(ProductVariant.sku.ilike(like), Product.name.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(StoreInventory.id.asc()).limit(limit).offset(offset)
    ).all()

    items: list[WhStoreInventoryOut] = []
    for inv, sku, product, category, health, vid in rows:
        on_floor = int(inv.on_floor or 0)
        backroom = int(inv.backroom or 0)
        qty = on_floor + backroom
        items.append(
            WhStoreInventoryOut(
                id=f"si-{inv.id}",
                sku=sku or "",
                product=product or sku or "",
                category=category or "General",
                qty=qty,
                onFloor=on_floor,
                backroom=backroom,
                reserved=int(inv.reserved or 0),
                reorder=int(inv.reorder_point or 0),
                bin=f"F{on_floor}/B{backroom}" if on_floor or backroom else "—",
                status=_staff_status(qty, str(health or "Healthy")),
                variant_id=int(vid or 0),
            )
        )

    return WhStoreInventoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        store_id=store.id,
        store_name=store.name or "",
        store_code=store.code or "",
    )
