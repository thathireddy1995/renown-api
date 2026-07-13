"""Admin stores — /admin/stores."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.inventory_status import store_stock_status
from app.database import get_db
from app.deps import pagination
from app.dto.location_dto import (
    StoreCreate,
    StoreInventoryListResponse,
    StoreInventoryOut,
    StoreListResponse,
    StoreOut,
    StoreUpdate,
)
from app.routers.admin_warehouses import case_dot_color
from app.schemas import Product, ProductVariant, Store, StoreInventory

router = APIRouter(prefix="/admin/stores", tags=["admin-stores"])


def _store_out(s: Store, skus: int = 0) -> StoreOut:
    return StoreOut(
        id=f"st-{s.id:02d}" if s.id < 100 else f"st-{s.id}",
        code=s.code,
        name=s.name,
        city=s.city or "",
        country=s.country or "",
        address=s.address or "",
        manager=s.manager or "",
        phone=s.phone or "",
        hours=s.hours or "",
        staff=s.staff or 0,
        skus=int(skus or 0),
        status=s.status or "Open",
        todayRevenue=float(s.today_revenue or 0),
        todayOrders=s.today_orders or 0,
    )


def _sku_stats_subq():
    return (
        select(
            StoreInventory.store_id.label("store_id"),
            func.count(StoreInventory.id).label("skus"),
        )
        .group_by(StoreInventory.store_id)
        .subquery()
    )


@router.get("", response_model=StoreListResponse)
def list_stores(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StoreListResponse:
    limit, offset = page
    stats = _sku_stats_subq()
    stmt = select(Store, stats.c.skus).outerjoin(stats, stats.c.store_id == Store.id)
    count_stmt = select(func.count()).select_from(Store)

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            Store.code.ilike(like),
            Store.name.ilike(like),
            Store.city.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(Store.id.asc()).limit(limit).offset(offset)
    ).all()
    return StoreListResponse(
        items=[_store_out(s, skus) for s, skus in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StoreOut, status_code=status.HTTP_201_CREATED)
def create_store(body: StoreCreate, db: Session = Depends(get_db)) -> StoreOut:
    if db.scalar(select(Store.id).where(Store.code == body.code)):
        raise HTTPException(status_code=409, detail="Store code already exists")
    row = Store(
        code=body.code.strip(),
        name=body.name.strip(),
        address=body.address,
        city=body.city,
        country=body.country,
        phone=body.phone,
        hours=body.hours,
        manager=body.manager,
        staff=body.staff,
        status=body.status or "Open",
        today_revenue=body.today_revenue,
        today_orders=body.today_orders,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _store_out(row)


@router.get("/inventory", response_model=StoreInventoryListResponse)
def list_all_store_inventory(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    store_id: int | None = None,
    store: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> StoreInventoryListResponse:
    return _list_store_inventory(
        db,
        page,
        store_id=store_id,
        store_name=store,
        status_filter=status_filter,
        search=search,
    )


@router.get("/{store_id}", response_model=StoreOut)
def get_store(store_id: int, db: Session = Depends(get_db)) -> StoreOut:
    s = db.get(Store, store_id)
    if not s:
        raise HTTPException(status_code=404, detail="Store not found")
    skus = (
        db.scalar(
            select(func.count()).where(StoreInventory.store_id == s.id)
        )
        or 0
    )
    return _store_out(s, skus)


@router.patch("/{store_id}", response_model=StoreOut)
def update_store(
    store_id: int, body: StoreUpdate, db: Session = Depends(get_db)
) -> StoreOut:
    s = db.get(Store, store_id)
    if not s:
        raise HTTPException(status_code=404, detail="Store not found")
    data = body.model_dump(exclude_unset=True)
    if "code" in data and data["code"]:
        clash = db.scalar(
            select(Store.id).where(Store.code == data["code"], Store.id != store_id)
        )
        if clash:
            raise HTTPException(status_code=409, detail="Store code already exists")
    for k, v in data.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return get_store(store_id, db)


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_store(store_id: int, db: Session = Depends(get_db)) -> None:
    s = db.get(Store, store_id)
    if not s:
        raise HTTPException(status_code=404, detail="Store not found")
    db.delete(s)
    db.commit()


@router.get("/{store_id}/inventory", response_model=StoreInventoryListResponse)
def list_store_inventory(
    store_id: int,
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> StoreInventoryListResponse:
    if not db.get(Store, store_id):
        raise HTTPException(status_code=404, detail="Store not found")
    return _list_store_inventory(
        db,
        page,
        store_id=store_id,
        status_filter=status_filter,
        search=search,
    )


def _list_store_inventory(
    db: Session,
    page: tuple[int, int],
    *,
    store_id: int | None = None,
    store_name: str | None = None,
    status_filter: str | None = None,
    search: str | None = None,
) -> StoreInventoryListResponse:
    limit, offset = page
    total_qty = StoreInventory.on_floor + StoreInventory.backroom
    status_col = store_stock_status(total_qty, StoreInventory.reorder_point).label(
        "stock_status"
    )
    product_label = func.concat(Product.name, case_dot_color()).label("product_label")

    stmt = (
        select(
            StoreInventory,
            Store.name,
            ProductVariant.sku,
            product_label,
            status_col,
        )
        .join(Store, Store.id == StoreInventory.store_id)
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
    )
    count_stmt = (
        select(func.count())
        .select_from(StoreInventory)
        .join(Store, Store.id == StoreInventory.store_id)
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
    )

    if store_id is not None:
        stmt = stmt.where(StoreInventory.store_id == store_id)
        count_stmt = count_stmt.where(StoreInventory.store_id == store_id)

    if store_name and store_name.strip() and store_name.lower() != "all":
        stmt = stmt.where(Store.name == store_name.strip())
        count_stmt = count_stmt.where(Store.name == store_name.strip())

    if status_filter:
        key = status_filter.strip().title()
        stmt = stmt.where(status_col == key)
        count_stmt = count_stmt.where(status_col == key)

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
        StoreInventoryOut(
            id=f"si-{row.id}",
            store=store_nm or "",
            sku=sku or "",
            product=product or "",
            onFloor=row.on_floor,
            backroom=row.backroom,
            reserved=row.reserved,
            reorder=row.reorder_point,
            status=stock_status,
        )
        for row, store_nm, sku, product, stock_status in rows
    ]
    return StoreInventoryListResponse(
        items=items, total=total, limit=limit, offset=offset
    )
