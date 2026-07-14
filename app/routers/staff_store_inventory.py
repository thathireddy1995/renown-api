"""Staff store inventory — /staff/store/inventory."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.inventory_status import store_stock_status
from app.database import get_db
from app.deps import pagination, require_role, TokenPrincipal
from app.routers.admin_warehouses import case_dot_color
from app.schemas import (
    Category,
    Product,
    ProductVariant,
    Store,
    StoreInventory,
    TransferRequest,
    Warehouse,
)

router = APIRouter(
    prefix="/staff/store/inventory",
    tags=["staff-store-inventory"],
    dependencies=[Depends(require_role("store_manager"))],
)


class StaffStoreInventoryOut(BaseModel):
    id: str
    sku: str
    product: str
    category: str
    qty: int
    bin: str
    status: str
    variant_id: int = 0


class StaffStoreInventoryListResponse(BaseModel):
    items: list[StaffStoreInventoryOut]
    total: int
    limit: int
    offset: int
    store_id: int | None = None
    store_name: str = ""


class StaffStockRequestCreate(BaseModel):
    sku: str | None = None
    variant_id: int | None = None
    product: str | None = None
    qty: int = Field(ge=1, le=10000)
    urgency: str = "Medium"
    store_id: int | None = None


class StaffStockRequestOut(BaseModel):
    id: str
    sku: str
    product: str
    qty: int
    urgency: str
    status: str
    message: str = ""


def _default_store(db: Session) -> Store | None:
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


def _resolve_store(db: Session, principal: TokenPrincipal, store_id: int | None) -> Store | None:
    sid = principal.store_id or store_id
    if sid is not None:
        return db.get(Store, sid)
    return _default_store(db)


def _staff_status(qty: int, health: str) -> str:
    if qty <= 0 or health == "Critical":
        return "Out of Stock" if qty <= 0 else "Low"
    if health == "Low":
        return "Low"
    return "In Stock"


def _bin_label(row: StoreInventory) -> str:
    floor = int(row.on_floor or 0)
    back = int(row.backroom or 0)
    if floor and back:
        return f"F{floor}/B{back}"
    if floor:
        return f"Floor-{row.id % 100:02d}"
    if back:
        return f"Back-{row.id % 100:02d}"
    return "—"


@router.get("", response_model=StaffStoreInventoryListResponse)
def list_inventory(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    store_id: int | None = None,
    search: str | None = Query(None, alias="q"),
) -> StaffStoreInventoryListResponse:
    limit, offset = page
    store = _resolve_store(db, principal, store_id)
    if not store:
        return StaffStoreInventoryListResponse(items=[], total=0, limit=limit, offset=offset)

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

    items = [
        StaffStoreInventoryOut(
            id=f"si-{inv.id}",
            sku=sku or "",
            product=product or sku or "",
            category=category or "General",
            qty=int(inv.on_floor or 0) + int(inv.backroom or 0),
            bin=_bin_label(inv),
            status=_staff_status(
                int(inv.on_floor or 0) + int(inv.backroom or 0),
                str(health or "Healthy"),
            ),
            variant_id=int(variant_id),
        )
        for inv, sku, product, category, health, variant_id in rows
    ]

    return StaffStoreInventoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        store_id=store.id,
        store_name=store.name or "",
    )


@router.post(
    "/stock-requests",
    response_model=StaffStockRequestOut,
    status_code=status.HTTP_201_CREATED,
)
def request_stock(
    body: StaffStockRequestCreate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffStockRequestOut:
    store = _resolve_store(db, principal, body.store_id)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")

    variant = None
    if body.variant_id is not None:
        variant = db.scalar(
            select(ProductVariant)
            .where(ProductVariant.id == body.variant_id)
            .options(selectinload(ProductVariant.product))
        )
    if not variant and body.sku:
        variant = db.scalar(
            select(ProductVariant)
            .where(ProductVariant.sku.ilike(body.sku.strip()))
            .options(selectinload(ProductVariant.product))
        )
    if not variant:
        raise HTTPException(status_code=404, detail="SKU / variant not found")

    warehouse = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
    if not warehouse:
        raise HTTPException(status_code=400, detail="No warehouse available to request from")

    urgency = (body.urgency or "Medium").strip().title()
    if urgency not in ("Low", "Medium", "High"):
        urgency = "Medium"

    num = f"REQ-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(TransferRequest.id).where(TransferRequest.request_number == num)):
        num = f"REQ-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    row = TransferRequest(
        request_number=num,
        store_id=store.id,
        target_warehouse_id=warehouse.id,
        variant_id=variant.id,
        qty_requested=body.qty,
        urgency=urgency,
        status="pending",
    )
    db.add(row)
    db.commit()

    product_name = body.product or (variant.product.name if variant.product else variant.sku)
    return StaffStockRequestOut(
        id=num,
        sku=variant.sku,
        product=product_name or variant.sku,
        qty=body.qty,
        urgency=urgency,
        status="Pending",
        message=f"Stock request {num} submitted for {body.qty} × {variant.sku}",
    )
