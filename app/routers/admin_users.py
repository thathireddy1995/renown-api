"""Admin users — /admin/users."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.staff_users import (
    MANAGED_ROLES,
    STAFF_ROLES,
    assign_user_location,
    create_staff_user,
    digits_phone,
    require_10_digit_phone,
)
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.user_dto import (
    AdminUserCounts,
    AdminUserCreate,
    AdminUserListResponse,
    AdminUserOut,
    AdminUserPasswordReset,
    AdminUserUpdate,
)
from app.schemas import Store, User, Warehouse

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_role("admin"))],
)


def _user_out(
    user: User,
    *,
    store_name: str | None = None,
    warehouse_name: str | None = None,
    store_code: str | None = None,
    warehouse_code: str | None = None,
    store_address: str | None = None,
    warehouse_address: str | None = None,
) -> AdminUserOut:
    kind = None
    loc_id = None
    loc_code = None
    loc_name = None
    loc_address = None
    if user.role == "store_manager" and user.store_id:
        kind = "store"
        loc_id = user.store_id
        loc_code = store_code
        loc_name = store_name
        loc_address = store_address
    elif user.role == "warehouse_manager" and user.warehouse_id:
        kind = "warehouse"
        loc_id = user.warehouse_id
        loc_code = warehouse_code
        loc_name = warehouse_name
        loc_address = warehouse_address
    return AdminUserOut(
        id=user.id,
        name=user.name,
        phone=user.phone,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        store_id=user.store_id,
        warehouse_id=user.warehouse_id,
        store_name=store_name,
        warehouse_name=warehouse_name,
        location_kind=kind,
        location_id=loc_id,
        location_code=loc_code,
        location_name=loc_name,
        location_address=loc_address,
        last_login=user.last_login,
        created_at=user.created_at,
    )


def _hydrate(db: Session, users: list[User]) -> list[AdminUserOut]:
    store_ids = [u.store_id for u in users if u.store_id is not None]
    warehouse_ids = [u.warehouse_id for u in users if u.warehouse_id is not None]
    stores: dict[int, tuple[str, str, str]] = {}
    warehouses: dict[int, tuple[str, str, str]] = {}
    if store_ids:
        for sid, name, code, address in db.execute(
            select(Store.id, Store.name, Store.code, Store.address).where(Store.id.in_(store_ids))
        ):
            stores[int(sid)] = (name, code or "", address or "")
    if warehouse_ids:
        for wid, name, code, address in db.execute(
            select(Warehouse.id, Warehouse.name, Warehouse.code, Warehouse.address).where(
                Warehouse.id.in_(warehouse_ids)
            )
        ):
            warehouses[int(wid)] = (name, code or "", address or "")
    out = []
    for user in users:
        s = stores.get(user.store_id) if user.store_id else None
        w = warehouses.get(user.warehouse_id) if user.warehouse_id else None
        out.append(
            _user_out(
                user,
                store_name=s[0] if s else None,
                store_code=s[1] if s else None,
                store_address=s[2] if s else None,
                warehouse_name=w[0] if w else None,
                warehouse_code=w[1] if w else None,
                warehouse_address=w[2] if w else None,
            )
        )
    return out


def _list_columns():
    return (
        User.id,
        User.name,
        User.phone,
        User.email,
        User.role,
        User.is_active,
        User.store_id,
        User.warehouse_id,
        User.last_login,
        User.created_at,
        Store.name.label("store_name"),
        Store.code.label("store_code"),
        Store.address.label("store_address"),
        Warehouse.name.label("warehouse_name"),
        Warehouse.code.label("warehouse_code"),
        Warehouse.address.label("warehouse_address"),
    )


def _row_out(row) -> AdminUserOut:
    kind = None
    loc_id = None
    loc_code = None
    loc_name = None
    loc_address = None
    if row.role == "store_manager" and row.store_id:
        kind = "store"
        loc_id = row.store_id
        loc_code = row.store_code
        loc_name = row.store_name
        loc_address = row.store_address
    elif row.role == "warehouse_manager" and row.warehouse_id:
        kind = "warehouse"
        loc_id = row.warehouse_id
        loc_code = row.warehouse_code
        loc_name = row.warehouse_name
        loc_address = row.warehouse_address
    return AdminUserOut(
        id=row.id,
        name=row.name,
        phone=row.phone,
        email=row.email,
        role=row.role,
        is_active=row.is_active,
        store_id=row.store_id,
        warehouse_id=row.warehouse_id,
        store_name=row.store_name,
        warehouse_name=row.warehouse_name,
        location_kind=kind,
        location_id=loc_id,
        location_code=loc_code,
        location_name=loc_name,
        location_address=loc_address,
        last_login=row.last_login,
        created_at=row.created_at,
    )


def _apply_user_filters(stmt, *, search: str | None, role: str | None, status_filter: str | None, unassigned: bool):
    if role:
        stmt = stmt.where(User.role == role)
    if status_filter == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status_filter == "inactive":
        stmt = stmt.where(User.is_active.is_(False))
    if unassigned:
        if role == "store_manager":
            stmt = stmt.where(User.store_id.is_(None))
        elif role == "warehouse_manager":
            stmt = stmt.where(User.warehouse_id.is_(None))
        else:
            stmt = stmt.where(User.store_id.is_(None), User.warehouse_id.is_(None))
    if search and search.strip():
        like = f"%{search.strip()}%"
        digits = digits_phone(search)
        filters = [User.name.ilike(like), User.email.ilike(like)]
        if digits:
            filters.append(User.phone.ilike(f"%{digits}%"))
        else:
            filters.append(User.phone.ilike(like))
        stmt = stmt.where(or_(*filters))
    return stmt


def _validate_location(db: Session, role: str, store_id: int | None, warehouse_id: int | None) -> None:
    if role == "store_manager" and store_id is not None:
        if not db.get(Store, store_id):
            raise HTTPException(status_code=400, detail="Store not found")
    if role == "warehouse_manager" and warehouse_id is not None:
        if not db.get(Warehouse, warehouse_id):
            raise HTTPException(status_code=400, detail="Warehouse not found")
    if role == "store_manager" and warehouse_id is not None and not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=400, detail="Warehouse not found")


@router.get("", response_model=AdminUserListResponse)
def list_users(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
    role: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    unassigned: bool = False,
) -> AdminUserListResponse:
    limit, offset = page
    filtered = bool((search and search.strip()) or role or status_filter or unassigned)
    kpi_total = select(func.count()).select_from(User).scalar_subquery()
    kpi_active = (
        select(func.count()).select_from(User).where(User.is_active.is_(True)).scalar_subquery()
    )
    filtered_total = (
        _apply_user_filters(
            select(func.count()).select_from(User),
            search=search,
            role=role,
            status_filter=status_filter,
            unassigned=unassigned,
        ).scalar_subquery()
        if filtered
        else kpi_total
    )
    rows = db.execute(
        _apply_user_filters(
            select(
                *_list_columns(),
                filtered_total.label("filtered_total"),
                kpi_total.label("kpi_total"),
                kpi_active.label("kpi_active"),
            )
            .select_from(User)
            .outerjoin(Store, Store.id == User.store_id)
            .outerjoin(Warehouse, Warehouse.id == User.warehouse_id),
            search=search,
            role=role,
            status_filter=status_filter,
            unassigned=unassigned,
        )
        .order_by(User.is_active.desc(), User.name.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    if rows:
        total = int(rows[0].filtered_total or 0)
        total_users = int(rows[0].kpi_total or 0)
        active = int(rows[0].kpi_active or 0)
    else:
        stats = db.execute(
            select(
                filtered_total.label("filtered_total"),
                kpi_total.label("kpi_total"),
                kpi_active.label("kpi_active"),
            )
        ).one()
        total = int(stats.filtered_total or 0)
        total_users = int(stats.kpi_total or 0)
        active = int(stats.kpi_active or 0)

    return AdminUserListResponse(
        items=[_row_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        counts=AdminUserCounts(total=total_users, active=active, inactive=total_users - active),
    )


@router.get("/assignable", response_model=AdminUserListResponse)
def list_assignable_users(
    role: str = Query(..., description="store_manager or warehouse_manager"),
    search: str | None = Query(None, alias="q"),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    if role not in STAFF_ROLES:
        raise HTTPException(status_code=400, detail="Role must be a staff manager role")
    stmt = _apply_user_filters(
        select(*_list_columns())
        .select_from(User)
        .outerjoin(Store, Store.id == User.store_id)
        .outerjoin(Warehouse, Warehouse.id == User.warehouse_id)
        .where(User.role == role, User.is_active.is_(True)),
        search=search,
        role=None,
        status_filter=None,
        unassigned=False,
    )
    rows = db.execute(
        stmt.order_by(
            User.store_id.is_not(None),
            User.warehouse_id.is_not(None),
            User.name.asc(),
        ).limit(50)
    ).all()
    items = [_row_out(row) for row in rows]
    return AdminUserListResponse(
        items=items,
        total=len(items),
        limit=len(items),
        offset=0,
        counts=AdminUserCounts(total=len(items), active=len(items), inactive=0),
    )


@router.post("", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: AdminUserCreate, db: Session = Depends(get_db)) -> AdminUserOut:
    role = (body.role or "").strip()
    if role not in MANAGED_ROLES:
        raise HTTPException(
            status_code=400,
            detail="Role must be admin, store_manager, or warehouse_manager",
        )
    phone = require_10_digit_phone(body.phone)
    if not body.password or len(body.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")

    store_id = body.store_id if role == "store_manager" else None
    warehouse_id = body.warehouse_id
    if role == "store_manager" and store_id:
        store = db.get(Store, store_id)
        if not store:
            raise HTTPException(status_code=400, detail="Store not found")
        warehouse_id = store.warehouse_id
    elif role == "warehouse_manager":
        store_id = None
    elif role == "admin":
        store_id = None
        warehouse_id = None
    _validate_location(db, role, store_id, warehouse_id)

    user = create_staff_user(
        db,
        name=body.name,
        phone=phone,
        password=body.password,
        role=role,
        store_id=store_id,
        warehouse_id=warehouse_id,
        is_active=body.is_active,
    )
    if role == "store_manager" and store_id:
        store = db.get(Store, store_id)
        if store:
            store.login_password = body.password
    if role == "warehouse_manager" and warehouse_id:
        warehouse = db.get(Warehouse, warehouse_id)
        if warehouse:
            warehouse.login_password = body.password
    db.commit()
    db.refresh(user)
    return _hydrate(db, [user])[0]


@router.get("/{user_id}", response_model=AdminUserOut)
def get_user(user_id: int, db: Session = Depends(get_db)) -> AdminUserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _hydrate(db, [user])[0]


@router.patch("/{user_id}", response_model=AdminUserOut)
def update_user(user_id: int, body: AdminUserUpdate, db: Session = Depends(get_db)) -> AdminUserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        if not data["name"].strip():
            raise HTTPException(status_code=400, detail="Name is required")
        user.name = data["name"].strip()
    if "phone" in data and data["phone"] is not None:
        phone = require_10_digit_phone(data["phone"])
        taken = db.scalar(select(User.id).where(User.phone == phone, User.id != user.id))
        if taken:
            raise HTTPException(status_code=409, detail="Phone already registered")
        user.phone = phone
    if "is_active" in data and data["is_active"] is not None:
        user.is_active = bool(data["is_active"])

    role = data.get("role") or user.role
    if role not in MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    store_id = data["store_id"] if "store_id" in data else user.store_id
    warehouse_id = data["warehouse_id"] if "warehouse_id" in data else user.warehouse_id
    if role == "store_manager" and store_id:
        store = db.get(Store, store_id)
        if not store:
            raise HTTPException(status_code=400, detail="Store not found")
        warehouse_id = store.warehouse_id
    elif role == "warehouse_manager":
        store_id = None
    elif role == "admin":
        store_id = None
        warehouse_id = None
    _validate_location(db, role, store_id, warehouse_id)
    assign_user_location(user, role=role, store_id=store_id, warehouse_id=warehouse_id)

    db.commit()
    db.refresh(user)
    return _hydrate(db, [user])[0]


@router.patch("/{user_id}/password", response_model=AdminUserOut)
def reset_user_password(
    user_id: int, body: AdminUserPasswordReset, db: Session = Depends(get_db)
) -> AdminUserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not body.password or len(body.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")
    user.password_hash = hash_password(body.password)
    if user.role == "store_manager" and user.store_id:
        store = db.get(Store, user.store_id)
        if store:
            store.login_password = body.password
    if user.role == "warehouse_manager" and user.warehouse_id:
        warehouse = db.get(Warehouse, user.warehouse_id)
        if warehouse:
            warehouse.login_password = body.password
    db.commit()
    db.refresh(user)
    return _hydrate(db, [user])[0]
