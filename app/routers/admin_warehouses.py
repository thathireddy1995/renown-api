"""Admin warehouses — /admin/warehouses."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.inventory_status import warehouse_stock_status
from app.core.security import hash_password
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.location_dto import (
    AdminInventoryAuditListResponse,
    AdminInventoryAuditOut,
    WarehouseCreate,
    WarehouseListResponse,
    WarehouseOut,
    WarehouseUpdate,
    WhInventoryListResponse,
    WhInventoryOut,
)
from app.schemas import InventoryAudit, Product, ProductVariant, User, Warehouse, WarehouseInventory

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


def _manager_for_warehouse(db: Session, warehouse_id: int) -> User | None:
    return db.scalar(
        select(User)
        .where(
            User.warehouse_id == warehouse_id,
            User.role == "warehouse_manager",
        )
        .order_by(User.id.asc())
        .limit(1)
    )


def _login_mobiles_map(db: Session, warehouse_ids: list[int]) -> dict[int, str]:
    if not warehouse_ids:
        return {}
    rows = db.execute(
        select(User.warehouse_id, User.phone)
        .where(
            User.warehouse_id.in_(warehouse_ids),
            User.role == "warehouse_manager",
            User.phone.isnot(None),
        )
        .order_by(User.id.asc())
    ).all()
    out: dict[int, str] = {}
    for wid, phone in rows:
        if wid is not None and wid not in out and phone:
            out[int(wid)] = phone
    return out


def _warehouse_out(
    w: Warehouse, used: int = 0, skus: int = 0, *, login_mobile: str | None = None
) -> WarehouseOut:
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
        login_mobile=login_mobile,
        login_password=w.login_password,
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
    mobiles = _login_mobiles_map(db, [w.id for w, _, _ in rows])
    return WarehouseListResponse(
        items=[
            _warehouse_out(w, used, skus, login_mobile=mobiles.get(w.id))
            for w, used, skus in rows
        ],
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

    mobile = body.login_mobile.strip()
    if len(mobile) != 10 or not mobile.isdigit():
        raise HTTPException(status_code=400, detail="Login mobile must be a 10-digit number")
    if len(body.login_password) < 4:
        raise HTTPException(status_code=400, detail="Login password must be at least 4 characters")

    phone_taken = db.scalar(select(User.id).where(User.phone == mobile))
    if phone_taken:
        raise HTTPException(status_code=409, detail="Login mobile is already registered")

    row = Warehouse(
        code=body.code.strip(),
        name=body.name.strip(),
        city=body.city,
        country=body.country,
        manager=body.manager,
        capacity=body.capacity,
        staff=body.staff,
        status=body.status or "Active",
        login_password=body.login_password,
    )
    db.add(row)
    db.flush()

    manager_name = (body.manager or "").strip() or f"{row.name} Manager"
    email = f"wh-{row.code.lower().replace(' ', '-')}@renown.local"
    email_taken = db.scalar(select(User.id).where(User.email == email))
    if email_taken:
        email = f"wh-{row.id}-{row.code.lower()}@renown.local"

    db.add(
        User(
            name=manager_name,
            email=email,
            phone=mobile,
            password_hash=hash_password(body.login_password),
            role="warehouse_manager",
            warehouse_id=row.id,
            is_active=True,
        )
    )
    db.commit()
    db.refresh(row)
    return _warehouse_out(row, login_mobile=mobile)


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
    manager = _manager_for_warehouse(db, w.id)
    return _warehouse_out(
        w, stats[0], stats[1], login_mobile=manager.phone if manager else None
    )


@router.patch("/{warehouse_id}", response_model=WarehouseOut)
def update_warehouse(
    warehouse_id: int, body: WarehouseUpdate, db: Session = Depends(get_db)
) -> WarehouseOut:
    w = db.get(Warehouse, warehouse_id)
    if not w:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    data = body.model_dump(exclude_unset=True)
    login_mobile = data.pop("login_mobile", None)
    login_password = data.pop("login_password", None)

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

    if login_mobile is not None or login_password is not None:
        manager = _manager_for_warehouse(db, warehouse_id)
        mobile = (login_mobile or "").strip() if login_mobile is not None else None

        if mobile is not None:
            if len(mobile) != 10 or not mobile.isdigit():
                raise HTTPException(
                    status_code=400, detail="Login mobile must be a 10-digit number"
                )
            phone_clash = db.scalar(
                select(User.id).where(
                    User.phone == mobile,
                    User.id != (manager.id if manager else -1),
                )
            )
            if phone_clash:
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
            email = f"wh-{w.code.lower().replace(' ', '-')}@renown.local"
            if db.scalar(select(User.id).where(User.email == email)):
                email = f"wh-{w.id}-{w.code.lower()}@renown.local"
            manager_name = (w.manager or "").strip() or f"{w.name} Manager"
            db.add(
                User(
                    name=manager_name,
                    email=email,
                    phone=mobile,
                    password_hash=hash_password(login_password),
                    role="warehouse_manager",
                    warehouse_id=w.id,
                    is_active=True,
                )
            )
            w.login_password = login_password
        else:
            if mobile is not None:
                manager.phone = mobile
            if login_password:
                manager.password_hash = hash_password(login_password)
                w.login_password = login_password
            if w.manager:
                manager.name = w.manager.strip()

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


_AUDIT_STATUS_UI = {
    "scheduled": "Scheduled",
    "in_progress": "In review",
    "completed": "Completed",
}


def _audit_date_label(row: InventoryAudit) -> str:
    when = row.completed_at or row.created_at
    if when is None:
        return "—"
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).date()
    d = when.date()
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    return d.isoformat()


@router.get("/inventory-audits", response_model=AdminInventoryAuditListResponse)
def list_inventory_audits(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> AdminInventoryAuditListResponse:
    limit, offset = page
    stmt = (
        select(InventoryAudit, Warehouse.name)
        .join(Warehouse, Warehouse.id == InventoryAudit.warehouse_id)
        .options(selectinload(InventoryAudit.items))
    )
    count_stmt = select(func.count()).select_from(InventoryAudit)
    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            InventoryAudit.audit_number.ilike(like),
            InventoryAudit.zone.ilike(like),
            InventoryAudit.auditor_name.ilike(like),
            Warehouse.name.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.join(
            Warehouse, Warehouse.id == InventoryAudit.warehouse_id
        ).where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(InventoryAudit.id.desc()).limit(limit).offset(offset)
    ).all()

    items: list[AdminInventoryAuditOut] = []
    for audit, wh_name in rows:
        items_list = audit.items or []
        scanned = sum(i.counted_qty for i in items_list)
        expected = sum(i.expected_qty for i in items_list)
        items.append(
            AdminInventoryAuditOut(
                id=audit.audit_number,
                warehouse=wh_name or "—",
                scope=audit.zone or "Cycle count",
                scanned=scanned,
                expected=expected,
                variance=scanned - expected,
                status=_AUDIT_STATUS_UI.get(audit.status, audit.status),
                date=_audit_date_label(audit),
            )
        )

    return AdminInventoryAuditListResponse(
        items=items, total=total, limit=limit, offset=offset
    )
