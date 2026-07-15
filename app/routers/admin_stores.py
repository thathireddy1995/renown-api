"""Admin stores — /admin/stores."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.inventory_status import store_stock_status
from app.core.security import hash_password
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.location_dto import (
    StoreCreate,
    StoreInventoryListResponse,
    StoreInventoryOut,
    StoreListResponse,
    StoreOut,
    StoreUpdate,
)
from app.schemas import Product, ProductVariant, Store, StoreInventory, User, Warehouse

router = APIRouter(prefix="/admin/stores", tags=["admin-stores"], dependencies=[Depends(require_role("admin"))])


def _manager_for_store(db: Session, store_id: int) -> User | None:
    return db.scalar(
        select(User)
        .where(User.store_id == store_id, User.role == "store_manager")
        .order_by(User.id.asc())
        .limit(1)
    )


def _login_mobiles_map(db: Session, store_ids: list[int]) -> dict[int, str]:
    if not store_ids:
        return {}
    rows = db.execute(
        select(User.store_id, User.phone)
        .where(
            User.store_id.in_(store_ids),
            User.role == "store_manager",
            User.phone.isnot(None),
        )
        .order_by(User.id.asc())
    ).all()
    out: dict[int, str] = {}
    for sid, phone in rows:
        if sid is not None and sid not in out and phone:
            out[int(sid)] = phone
    return out


def _warehouse_names_map(db: Session, warehouse_ids: list[int]) -> dict[int, str]:
    if not warehouse_ids:
        return {}
    rows = db.execute(
        select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(warehouse_ids))
    ).all()
    return {int(wid): name for wid, name in rows}


def _store_out(
    s: Store,
    skus: int = 0,
    *,
    login_mobile: str | None = None,
    warehouse_name: str | None = None,
) -> StoreOut:
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
        warehouse_id=s.warehouse_id,
        warehouse_name=warehouse_name,
        login_mobile=login_mobile,
        login_password=s.login_password,
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
    mobiles = _login_mobiles_map(db, [s.id for s, _ in rows])
    wh_names = _warehouse_names_map(
        db, [s.warehouse_id for s, _ in rows if s.warehouse_id is not None]
    )
    return StoreListResponse(
        items=[
            _store_out(
                s,
                skus,
                login_mobile=mobiles.get(s.id),
                warehouse_name=wh_names.get(s.warehouse_id) if s.warehouse_id else None,
            )
            for s, skus in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StoreOut, status_code=status.HTTP_201_CREATED)
def create_store(body: StoreCreate, db: Session = Depends(get_db)) -> StoreOut:
    if db.scalar(select(Store.id).where(Store.code == body.code)):
        raise HTTPException(status_code=409, detail="Store code already exists")

    wh = db.get(Warehouse, body.warehouse_id)
    if not wh:
        raise HTTPException(status_code=400, detail="Selected warehouse not found")

    mobile = body.login_mobile.strip()
    if len(mobile) != 10 or not mobile.isdigit():
        raise HTTPException(status_code=400, detail="Login mobile must be a 10-digit number")
    if len(body.login_password) < 4:
        raise HTTPException(status_code=400, detail="Login password must be at least 4 characters")
    if db.scalar(select(User.id).where(User.phone == mobile)):
        raise HTTPException(status_code=409, detail="Login mobile is already registered")

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
        warehouse_id=body.warehouse_id,
        login_password=body.login_password,
    )
    db.add(row)
    db.flush()

    manager_name = (body.manager or "").strip() or f"{row.name} Manager"
    email = f"st-{row.code.lower().replace(' ', '-')}@renown.local"
    if db.scalar(select(User.id).where(User.email == email)):
        email = f"st-{row.id}-{row.code.lower()}@renown.local"

    db.add(
        User(
            name=manager_name,
            email=email,
            phone=mobile,
            password_hash=hash_password(body.login_password),
            role="store_manager",
            store_id=row.id,
            warehouse_id=body.warehouse_id,
            is_active=True,
        )
    )
    db.commit()
    db.refresh(row)
    return _store_out(row, login_mobile=mobile, warehouse_name=wh.name)


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
    manager = _manager_for_store(db, s.id)
    wh_name = None
    if s.warehouse_id:
        wh = db.get(Warehouse, s.warehouse_id)
        wh_name = wh.name if wh else None
    return _store_out(
        s,
        skus,
        login_mobile=manager.phone if manager else None,
        warehouse_name=wh_name,
    )


@router.patch("/{store_id}", response_model=StoreOut)
def update_store(
    store_id: int, body: StoreUpdate, db: Session = Depends(get_db)
) -> StoreOut:
    s = db.get(Store, store_id)
    if not s:
        raise HTTPException(status_code=404, detail="Store not found")
    data = body.model_dump(exclude_unset=True)
    login_mobile = data.pop("login_mobile", None)
    login_password = data.pop("login_password", None)

    if "code" in data and data["code"]:
        clash = db.scalar(
            select(Store.id).where(Store.code == data["code"], Store.id != store_id)
        )
        if clash:
            raise HTTPException(status_code=409, detail="Store code already exists")

    if "warehouse_id" in data and data["warehouse_id"] is not None:
        if not db.get(Warehouse, data["warehouse_id"]):
            raise HTTPException(status_code=400, detail="Selected warehouse not found")

    for k, v in data.items():
        setattr(s, k, v)

    if login_mobile is not None or login_password is not None:
        manager = _manager_for_store(db, store_id)
        mobile = (login_mobile or "").strip() if login_mobile is not None else None

        if mobile is not None:
            if len(mobile) != 10 or not mobile.isdigit():
                raise HTTPException(
                    status_code=400, detail="Login mobile must be a 10-digit number"
                )
            clash = db.scalar(
                select(User.id).where(
                    User.phone == mobile,
                    User.id != (manager.id if manager else -1),
                )
            )
            if clash:
                raise HTTPException(
                    status_code=409, detail="Login mobile is already registered"
                )

        if login_password is not None and login_password != "" and len(login_password) < 4:
            raise HTTPException(
                status_code=400, detail="Login password must be at least 4 characters"
            )

        if manager is None:
            if not mobile or not login_password:
                raise HTTPException(
                    status_code=400,
                    detail="Both login mobile and password are required to create a manager login",
                )
            email = f"st-{s.code.lower().replace(' ', '-')}@renown.local"
            if db.scalar(select(User.id).where(User.email == email)):
                email = f"st-{s.id}-{s.code.lower()}@renown.local"
            manager_name = (s.manager or "").strip() or f"{s.name} Manager"
            db.add(
                User(
                    name=manager_name,
                    email=email,
                    phone=mobile,
                    password_hash=hash_password(login_password),
                    role="store_manager",
                    store_id=s.id,
                    warehouse_id=s.warehouse_id,
                    is_active=True,
                )
            )
            s.login_password = login_password
        else:
            if mobile is not None:
                manager.phone = mobile
            if login_password:
                manager.password_hash = hash_password(login_password)
                s.login_password = login_password
            if s.manager:
                manager.name = s.manager.strip()
            if s.warehouse_id is not None:
                manager.warehouse_id = s.warehouse_id

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
    status_col = store_stock_status(
        StoreInventory.on_floor + StoreInventory.backroom,
        StoreInventory.reorder_point,
    )
    stmt = (
        select(
            StoreInventory,
            ProductVariant,
            Product,
            Store,
            status_col.label("stock_status"),
        )
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Store, Store.id == StoreInventory.store_id)
    )
    count_stmt = select(func.count()).select_from(StoreInventory)

    if store_id is not None:
        stmt = stmt.where(StoreInventory.store_id == store_id)
        count_stmt = count_stmt.where(StoreInventory.store_id == store_id)
    if store_name and store_name.strip() and store_name != "All":
        stmt = stmt.where(Store.name.ilike(f"%{store_name.strip()}%"))
        count_stmt = count_stmt.where(
            StoreInventory.store_id.in_(
                select(Store.id).where(Store.name.ilike(f"%{store_name.strip()}%"))
            )
        )
    if status_filter and status_filter.strip() and status_filter != "All":
        stmt = stmt.where(status_col == status_filter.strip())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ProductVariant.sku.ilike(like),
                Product.name.ilike(like),
                Store.name.ilike(like),
            )
        )

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(StoreInventory.id.asc()).limit(limit).offset(offset)
    ).all()

    items = []
    for inv, variant, product, store, stock_status in rows:
        color = f" · {variant.color}" if variant.color else ""
        items.append(
            StoreInventoryOut(
                id=f"si-{inv.id}",
                store=store.name,
                sku=variant.sku,
                product=f"{product.name}{color}",
                onFloor=inv.on_floor or 0,
                backroom=inv.backroom or 0,
                reserved=inv.reserved or 0,
                reorder=inv.reorder_point or 0,
                status=stock_status,
            )
        )
    return StoreInventoryListResponse(
        items=items, total=total, limit=limit, offset=offset
    )
