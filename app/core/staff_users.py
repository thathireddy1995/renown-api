"""Shared helpers for admin/staff login users."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ist import naive_now
from app.core.security import hash_password
from app.schemas import Store, User, Warehouse

MANAGED_ROLES = frozenset({"admin", "store_manager", "warehouse_manager"})
STAFF_ROLES = frozenset({"store_manager", "warehouse_manager"})


def digits_phone(raw: str | None) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def require_10_digit_phone(raw: str | None) -> str:
    phone = digits_phone(raw)
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="A valid 10-digit phone is required")
    return phone


def unique_staff_email(db: Session, role: str, phone: str, extra: str = "") -> str:
    email = f"{role}.{phone}@staff.renown.local"
    if extra:
        email = f"{role}.{phone}.{extra}@staff.renown.local"
    if db.scalar(select(User.id).where(User.email == email)):
        email = f"{role}.{phone}.{naive_now().strftime('%H%M%S')}@staff.renown.local"
    return email


def get_user_by_phone(db: Session, phone: str) -> User | None:
    return db.scalar(select(User).where(User.phone == phone))


def stamp_last_login(db: Session, user: User) -> None:
    user.last_login = naive_now()
    db.add(user)
    db.commit()


def assign_user_location(
    user: User,
    *,
    role: str | None = None,
    store_id: int | None = None,
    warehouse_id: int | None = None,
) -> User:
    target_role = role or user.role
    if target_role == "store_manager":
        user.role = "store_manager"
        user.store_id = store_id
        user.warehouse_id = warehouse_id
    elif target_role == "warehouse_manager":
        user.role = "warehouse_manager"
        user.warehouse_id = warehouse_id
        user.store_id = None
    else:
        user.role = target_role
        user.store_id = None
        user.warehouse_id = None
    return user


def require_assignable_user(db: Session, user_id: int, expected_role: str) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != expected_role:
        raise HTTPException(
            status_code=400,
            detail=f"User must have role {expected_role}",
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="User is inactive")
    if not user.phone or len("".join(ch for ch in user.phone if ch.isdigit())) != 10:
        raise HTTPException(status_code=400, detail="User needs a 10-digit phone to sign in")
    return user


def create_staff_user(
    db: Session,
    *,
    name: str,
    phone: str,
    password: str,
    role: str,
    store_id: int | None = None,
    warehouse_id: int | None = None,
    is_active: bool = True,
    email: str | None = None,
) -> User:
    if role not in MANAGED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")
    if db.scalar(select(User.id).where(User.phone == phone)):
        raise HTTPException(status_code=409, detail="Phone already registered")
    resolved_email = email or unique_staff_email(db, role, phone)
    if db.scalar(select(User.id).where(User.email == resolved_email)):
        resolved_email = unique_staff_email(db, role, phone, extra=str(phone)[-4:])
    row = User(
        name=name.strip(),
        email=resolved_email,
        phone=phone,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
    )
    assign_user_location(row, role=role, store_id=store_id, warehouse_id=warehouse_id)
    db.add(row)
    return row


def location_names(db: Session, store_ids: list[int], warehouse_ids: list[int]) -> tuple[dict[int, str], dict[int, str]]:
    stores: dict[int, str] = {}
    warehouses: dict[int, str] = {}
    if store_ids:
        for sid, name in db.execute(
            select(Store.id, Store.name).where(Store.id.in_(store_ids))
        ):
            stores[int(sid)] = name
    if warehouse_ids:
        for wid, name in db.execute(
            select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(warehouse_ids))
        ):
            warehouses[int(wid)] = name
    return stores, warehouses
