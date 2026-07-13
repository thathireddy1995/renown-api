"""Admin warehouses — /admin/warehouses."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.inventory_status import warehouse_stock_status
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.location_dto import (
    WarehouseCreate,
    WarehouseListResponse,
    WarehouseOut,
    WarehouseUpdate,
    WhInventoryListResponse,
    WhInventoryOut,
)
from app.schemas import Product, ProductVariant, Warehouse, WarehouseInventory

router = APIRouter(prefix="/admin/warehouses", tags=["admin-warehouses"], dependencies=[Depends(require_role("admin"))])


def case_dot_color():
    from sqlalchemy import case, literal

    return case(
        (
            ProductVariant.color.isnot(None),
            func.concat(literal(" · "), ProductVariant.color),
        ),
        else_=literal(""),
    )


def _warehouse_out(w: Warehouse, used: int = 0, skus: int = 0) -> WarehouseOut:
    return WarehouseOut(
        id=f"w-{w.id:02d}" if w.id < 100 else f"w-{w.id}",
        code=w.code,
        name=w.name,
        city=w.city or "",
        country=w.country or "",
        manager=w.manager or "",
        capacity=w.capacity or 0,
        used=int(used or 0),
        skus=int(skus or 0),
        staff=w.staff or 0,
        status=w.status or "Active",
    )


def _stats_subq():
    return (
        select(
            WarehouseInventory.warehouse_id.label("warehouse_id"),
            func.coalesce(func.sum(WarehouseInventory.on_hand), 0).label("used"),
            func.count(WarehouseInventory.id).label("skus"),
        )
        .group_by(WarehouseInventory.warehouse_id)
        .subquery()
    )


@router.get("", response_model=WarehouseListResponse)
def list_warehouses(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> WarehouseListResponse:
    limit, offset = page
    stats = _stats_subq()
    stmt = select(Warehouse, stats.c.used, stats.c.skus).outerjoin(
        stats, stats.c.warehouse_id == Warehouse.id
    )
    count_stmt = select(func.count()).select_from(Warehouse)

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            Warehouse.code.ilike(like),
            Warehouse.name.ilike(like),
            Warehouse.city.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(Warehouse.id.asc()).limit(limit).offset(offset)
    ).all()
    return WarehouseListResponse(
        items=[_warehouse_out(w, used, skus) for w, used, skus in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
def create_warehouse(
    body: WarehouseCreate, db: Session = Depends(get_db)
) -> WarehouseOut:
    existing = db.scalar(select(Warehouse.id).where(Warehouse.code == body.code))
    if existing:
        raise HTTPException(status_code=409, detail="Warehouse code already exists")
    row = Warehouse(
        code=body.code.strip(),
        name=body.name.strip(),
        city=body.city,
        country=body.country,
        manager=body.manager,
        capacity=body.capacity,
        staff=body.staff,
        status=body.status or "Active",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _warehouse_out(row)


@router.get("/inventory", response_model=WhInventoryListResponse)
def list_all_warehouse_inventory(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    warehouse_id: int | None = None,
    warehouse: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> WhInventoryListResponse:
    return _list_wh_inventory(
        db,
        page,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse,
        status_filter=status_filter,
        search=search,
    )


@router.get("/{warehouse_id}", response_model=WarehouseOut)
def get_warehouse(warehouse_id: int, db: Session = Depends(get_db)) -> WarehouseOut:
    w = db.get(Warehouse, warehouse_id)
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    stats = db.execute(
        select(
            func.coalesce(func.sum(WarehouseInventory.on_hand), 0),
            func.count(WarehouseInventory.id),
        ).where(WarehouseInventory.warehouse_id == w.id)
    ).one()
    return _warehouse_out(w, stats[0], stats[1])


@router.patch("/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(
    warehouse_id: int, body: WarehouseUpdate, db: Session = Depends(get_db)
) -> WarehouseOut:
    w = db.get(Warehouse, warehouse_id)
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    data = body.model_dump(exclude_unset=True)
    if "code" in data and data["code"]:
        clash = db.scalar(
            select(Warehouse.id).where(
                Warehouse.code == data["code"], Warehouse.id != warehouse_id
            )
        )
        if clash:
            raise HTTPException(status_code=409, detail="Warehouse code already exists")
    for k, v in data.items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return get_warehouse(warehouse_id, db)


@router.delete("/{warehouse_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db)) -> None:
    w = db.get(Warehouse, warehouse_id)
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    db.delete(w)
    db.commit()


@router.get("/{warehouse_id}/inventory", response_model=WhInventoryListResponse)
def list_warehouse_inventory(
    warehouse_id: int,
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> WhInventoryListResponse:
    if not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return _list_wh_inventory(
        db,
        page,
        warehouse_id=warehouse_id,
        status_filter=status_filter,
        search=search,
    )


def _list_wh_inventory(
    db: Session,
    page: tuple[int, int],
    *,
    warehouse_id: int | None = None,
    warehouse_name: str | None = None,
    status_filter: str | None = None,
    search: str | None = None,
) -> WhInventoryListResponse:
    limit, offset = page
    status_col = warehouse_stock_status(
        WarehouseInventory.on_hand, WarehouseInventory.reorder_point
    ).label("stock_status")
    product_label = func.concat(Product.name, case_dot_color()).label("product_label")

    stmt = (
        select(
            WarehouseInventory,
            Warehouse.name,
            ProductVariant.sku,
            product_label,
            status_col,
        )
        .join(Warehouse, Warehouse.id == WarehouseInventory.warehouse_id)
        .join(ProductVariant, ProductVariant.id == WarehouseInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
    )
    count_stmt = (
        select(func.count())
        .select_from(WarehouseInventory)
        .join(Warehouse, Warehouse.id == WarehouseInventory.warehouse_id)
        .join(ProductVariant, ProductVariant.id == WarehouseInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
    )

    if warehouse_id is not None:
        stmt = stmt.where(WarehouseInventory.warehouse_id == warehouse_id)
        count_stmt = count_stmt.where(WarehouseInventory.warehouse_id == warehouse_id)

    if warehouse_name and warehouse_name.strip() and warehouse_name != "All":
        stmt = stmt.where(Warehouse.name == warehouse_name.strip())
        count_stmt = count_stmt.where(Warehouse.name == warehouse_name.strip())

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
        stmt.order_by(WarehouseInventory.id.asc()).limit(limit).offset(offset)
    ).all()

    items = [
        WhInventoryOut(
            id=f"inv-{row.id}",
            sku=sku or "",
            product=product or "",
            warehouse=wh_name or "",
            bin=row.bin_location or "",
            onHand=row.on_hand,
            reserved=row.reserved,
            reorder=row.reorder_point,
            status=stock_status,
        )
        for row, wh_name, sku, product, stock_status in rows
    ]
    return WhInventoryListResponse(
        items=items, total=total, limit=limit, offset=offset
    )
