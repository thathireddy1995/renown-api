"""Staff store inventory — /staff/store/inventory."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.inventory_status import store_stock_status
from app.core.ist import format_ist_date
from app.core.stock_requests import (
    create_store_request,
    request_eager_options,
    request_lines,
    store_source_warehouse,
    variant_image,
    variant_label,
)
from app.core.stock_transfers import admin_status_label
from app.database import get_db
from app.deps import pagination, require_role, TokenPrincipal
from app.routers.admin_warehouses import case_dot_color
from app.schemas import (
    Brand,
    Category,
    Color,
    Product,
    ProductImage,
    ProductVariant,
    Size,
    StockTransfer,
    StockTransferItem,
    Store,
    StoreInventory,
    TransferRequest,
    TransferRequestItem,
    WarehouseInventory,
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
    product_id: str = ""
    price: float = 0
    product_key: int = 0
    name: str = ""
    size: str = ""
    color: str = ""
    color_hex: str | None = None
    image: str | None = None


class StaffStoreInventoryListResponse(BaseModel):
    items: list[StaffStoreInventoryOut]
    total: int
    limit: int
    offset: int
    store_id: int | None = None
    store_name: str = ""


class StaffStockRequestLineIn(BaseModel):
    variant_id: int
    qty: int = Field(ge=1, le=10000)


class StaffStockRequestCreate(BaseModel):
    sku: str | None = None
    variant_id: int | None = None
    product: str | None = None
    qty: int | None = Field(default=None, ge=1, le=10000)
    items: list[StaffStockRequestLineIn] = Field(default_factory=list, max_length=200)
    urgency: str = "Medium"
    store_id: int | None = None


class StaffStockRequestLineOut(BaseModel):
    variant_id: int
    sku: str
    name: str
    color: str = ""
    size: str = ""
    image: str | None = None
    qty: int


class StaffStockRequestOut(BaseModel):
    id: str
    sku: str
    product: str
    qty: int
    urgency: str
    status: str
    message: str = ""
    date: str = ""
    lines: list[StaffStockRequestLineOut] = []
    transfer: str | None = None
    transfer_status: str | None = None


class StaffStockRequestListResponse(BaseModel):
    items: list[StaffStockRequestOut]
    store_name: str = ""


class WarehouseStockItemOut(BaseModel):
    variant_id: int
    sku: str
    product_key: int
    product_id: str = ""
    name: str
    category: str
    brand: str = ""
    color: str = ""
    color_hex: str | None = None
    size: str = ""
    image: str | None = None
    price: float = 0
    warehouse_qty: int = 0
    store_qty: int = 0
    incoming_qty: int = 0


class WarehouseStockResponse(BaseModel):
    items: list[WarehouseStockItemOut]
    warehouse_name: str = ""
    store_name: str = ""


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
            func.coalesce(Product.product_id, Product.sku, ""),
            func.coalesce(ProductVariant.price, Product.selling_price, Product.price, 0),
            Product.id,
            Product.name,
            func.coalesce(Size.name, ProductVariant.size, ""),
            func.coalesce(Color.name, ProductVariant.color, ""),
            func.coalesce(Color.hex, ProductVariant.color_hex),
            select(ProductImage.url)
            .where(ProductImage.product_id == Product.id)
            .order_by(ProductImage.sort_order.asc(), ProductImage.id.asc())
            .limit(1)
            .scalar_subquery(),
        )
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .outerjoin(Size, Size.id == ProductVariant.size_id)
        .outerjoin(Color, Color.id == ProductVariant.color_id)
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
            product_id=product_id or "",
            price=float(price or 0),
            product_key=int(product_key),
            name=name or "",
            size="" if size == "__deleted__" else (size or ""),
            color="" if color == "__deleted__" else (color or ""),
            color_hex=color_hex,
            image=image,
        )
        for (
            inv,
            sku,
            product,
            category,
            health,
            variant_id,
            product_id,
            price,
            product_key,
            name,
            size,
            color,
            color_hex,
            image,
        ) in rows
    ]

    return StaffStoreInventoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        store_id=store.id,
        store_name=store.name or "",
    )


def _request_out(req: TransferRequest) -> StaffStockRequestOut:
    lines = request_lines(req)
    first = lines[0].variant if lines else None
    total = sum(line.qty for line in lines)
    transfer = req.stock_transfer
    return StaffStockRequestOut(
        id=req.request_number,
        sku=first.sku if first else "",
        product=(first.product.name if first and first.product else "") or (first.sku if first else ""),
        qty=total,
        urgency=req.urgency or "Medium",
        status=(req.status or "pending").title(),
        date=format_ist_date(req.created_at),
        lines=[
            StaffStockRequestLineOut(
                variant_id=line.variant.id,
                sku=line.variant.sku,
                name=line.variant.product.name if line.variant.product else line.variant.sku,
                color=variant_label(line.variant.color),
                size=variant_label(line.variant.size),
                image=variant_image(line.variant),
                qty=line.qty,
            )
            for line in lines
        ],
        transfer=transfer.transfer_number if transfer else None,
        transfer_status=admin_status_label(transfer.status) if transfer else None,
    )


@router.get("/warehouse-stock", response_model=WarehouseStockResponse)
def warehouse_stock(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    store_id: int | None = None,
) -> WarehouseStockResponse:
    """Active catalog with what the source warehouse can send and what this store holds."""
    store = _resolve_store(db, principal, store_id)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")
    warehouse = store_source_warehouse(db, store)
    if not warehouse:
        raise HTTPException(status_code=400, detail="No warehouse available to request from")

    wh_qty = (
        select(func.coalesce(func.sum(WarehouseInventory.on_hand - WarehouseInventory.reserved), 0))
        .where(
            WarehouseInventory.warehouse_id == warehouse.id,
            WarehouseInventory.variant_id == ProductVariant.id,
        )
        .scalar_subquery()
    )
    store_qty = (
        select(func.coalesce(func.sum(StoreInventory.on_floor + StoreInventory.backroom), 0))
        .where(
            StoreInventory.store_id == store.id,
            StoreInventory.variant_id == ProductVariant.id,
        )
        .scalar_subquery()
    )
    pending_qty = (
        select(func.coalesce(func.sum(TransferRequestItem.qty), 0))
        .join(TransferRequest, TransferRequest.id == TransferRequestItem.transfer_request_id)
        .where(
            TransferRequest.store_id == store.id,
            TransferRequest.status == "pending",
            TransferRequestItem.variant_id == ProductVariant.id,
        )
        .scalar_subquery()
    )
    transit_qty = (
        select(func.coalesce(func.sum(StockTransferItem.qty), 0))
        .join(StockTransfer, StockTransfer.id == StockTransferItem.stock_transfer_id)
        .where(
            StockTransfer.to_store_id == store.id,
            StockTransfer.status.in_(("approved", "picking", "packing", "in_transit")),
            StockTransferItem.variant_id == ProductVariant.id,
        )
        .scalar_subquery()
    )
    product_image = (
        select(ProductImage.url)
        .where(ProductImage.product_id == Product.id)
        .order_by(ProductImage.sort_order.asc(), ProductImage.id.asc())
        .limit(1)
        .scalar_subquery()
    )

    rows = db.execute(
        select(
            ProductVariant.id,
            ProductVariant.sku,
            Product.id,
            func.coalesce(Product.product_id, Product.sku, ""),
            Product.name,
            func.coalesce(Category.name, "General"),
            func.coalesce(Brand.name, ""),
            func.coalesce(Color.name, ProductVariant.color, ""),
            func.coalesce(Color.hex, ProductVariant.color_hex),
            func.coalesce(Size.name, ProductVariant.size, ""),
            func.coalesce(ProductVariant.images.op("->>")(0), product_image),
            func.coalesce(ProductVariant.price, Product.selling_price, Product.price, 0),
            wh_qty,
            store_qty,
            pending_qty + transit_qty,
        )
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .outerjoin(Brand, Brand.id == Product.brand_id)
        .outerjoin(Size, Size.id == ProductVariant.size_id)
        .outerjoin(Color, Color.id == ProductVariant.color_id)
        .where(
            Product.status == "active",
            func.coalesce(ProductVariant.color, "") != "__deleted__",
            func.coalesce(ProductVariant.size, "") != "__deleted__",
        )
        .order_by(Product.name.asc(), Product.id.asc(), ProductVariant.id.asc())
    ).all()

    return WarehouseStockResponse(
        items=[
            WarehouseStockItemOut(
                variant_id=vid,
                sku=sku,
                product_key=pid,
                product_id=product_code or "",
                name=name or sku,
                category=category or "General",
                brand=brand or "",
                color=variant_label(color),
                color_hex=color_hex,
                size=variant_label(size),
                image=image,
                price=float(price or 0),
                warehouse_qty=max(0, int(wq or 0)),
                store_qty=int(sq or 0),
                incoming_qty=int(iq or 0),
            )
            for (
                vid, sku, pid, product_code, name, category, brand,
                color, color_hex, size, image, price, wq, sq, iq,
            ) in rows
        ],
        warehouse_name=warehouse.name or "",
        store_name=store.name or "",
    )


@router.get("/stock-requests", response_model=StaffStockRequestListResponse)
def list_stock_requests(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    store_id: int | None = None,
    limit: int = Query(30, ge=1, le=100),
) -> StaffStockRequestListResponse:
    store = _resolve_store(db, principal, store_id)
    if not store:
        return StaffStockRequestListResponse(items=[])
    rows = db.scalars(
        select(TransferRequest)
        .options(*request_eager_options())
        .where(TransferRequest.store_id == store.id)
        .order_by(TransferRequest.id.desc())
        .limit(limit)
    ).all()
    return StaffStockRequestListResponse(
        items=[_request_out(r) for r in rows], store_name=store.name or ""
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

    lines = [(line.variant_id, line.qty) for line in body.items]
    if not lines:
        variant = None
        if body.variant_id is not None:
            variant = db.get(ProductVariant, body.variant_id)
        if not variant and body.sku:
            variant = db.scalar(
                select(ProductVariant).where(ProductVariant.sku.ilike(body.sku.strip()))
            )
        if not variant:
            raise HTTPException(status_code=404, detail="SKU / variant not found")
        if not body.qty:
            raise HTTPException(status_code=422, detail="Quantity must be at least 1")
        lines = [(variant.id, body.qty)]

    warehouse = store_source_warehouse(db, store)
    if not warehouse:
        raise HTTPException(status_code=400, detail="No warehouse available to request from")

    req = create_store_request(
        db, store=store, warehouse=warehouse, lines=lines, urgency=body.urgency
    )
    db.commit()

    loaded = db.scalar(
        select(TransferRequest)
        .options(*request_eager_options())
        .where(TransferRequest.id == req.id)
    )
    assert loaded
    out = _request_out(loaded)
    count = len(out.lines)
    out.message = (
        f"Stock request {out.id} sent to {warehouse.name}: "
        f"{count} item{'s' if count != 1 else ''}, {out.qty} unit{'s' if out.qty != 1 else ''}"
    )
    return out
