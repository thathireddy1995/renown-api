"""Staff auth — /staff/auth."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.dto.auth_dto import StaffLoginRequest, TokenResponse, UserOut
from app.dto.location_dto import (
    StoreLoginOption,
    StoreLoginOptionList,
    WarehouseLoginOption,
    WarehouseLoginOptionList,
)
from app.schemas import Store, User, Warehouse

router = APIRouter(prefix="/staff/auth", tags=["staff-auth"])

STAFF_ROLES = {"warehouse_manager", "store_manager", "staff"}


def _user_out(
    user: User,
    *,
    warehouse: Warehouse | None = None,
    store: Store | None = None,
) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        warehouse_id=user.warehouse_id if warehouse is None else (warehouse.id if warehouse else user.warehouse_id),
        store_id=user.store_id if store is None else (store.id if store else user.store_id),
        warehouse_code=warehouse.code if warehouse else None,
        warehouse_name=warehouse.name if warehouse else None,
        warehouse_city=warehouse.city if warehouse else None,
        store_code=store.code if store else None,
        store_name=store.name if store else None,
        store_city=store.city if store else None,
    )


@router.get("/warehouses", response_model=WarehouseLoginOptionList)
def list_login_warehouses(db: Session = Depends(get_db)):
    """Public list of active warehouses for the staff login location dropdown."""
    rows = db.scalars(
        select(Warehouse)
        .where(
            or_(
                Warehouse.status.is_(None),
                func.lower(Warehouse.status).notin_(("inactive", "closed", "disabled")),
            )
        )
        .order_by(Warehouse.name)
    ).all()
    items = [
        WarehouseLoginOption(
            id=w.id,
            code=w.code,
            name=w.name,
            city=w.city or "",
            label=f"{w.name} · {w.city}" if w.city else w.name,
        )
        for w in rows
    ]
    return WarehouseLoginOptionList(items=items)


@router.get("/stores", response_model=StoreLoginOptionList)
def list_login_stores(
    warehouse_id: int = Query(..., description="Required — only stores under this warehouse"),
    db: Session = Depends(get_db),
):
    """Public list of open stores for a warehouse (used at store-manager login)."""
    stmt = (
        select(Store)
        .where(
            Store.warehouse_id == warehouse_id,
            or_(
                Store.status.is_(None),
                func.lower(Store.status).notin_(("closed", "inactive", "disabled")),
            ),
        )
        .order_by(Store.name)
    )
    rows = db.scalars(stmt).all()
    items = [
        StoreLoginOption(
            id=s.id,
            code=s.code,
            name=s.name,
            city=s.city or "",
            warehouse_id=s.warehouse_id,
            label=f"{s.name} · {s.city}" if s.city else s.name,
        )
        for s in rows
    ]
    return StoreLoginOptionList(items=items)


@router.post("/login", response_model=TokenResponse)
def staff_login(body: StaffLoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.phone == body.phone))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    if user.role not in STAFF_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a staff account")

    warehouse: Warehouse | None = None
    store: Store | None = None

    if user.role == "warehouse_manager":
        if body.warehouse_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please select a warehouse location",
            )
        if user.warehouse_id is None or user.warehouse_id != body.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="These credentials are not valid for the selected warehouse",
            )
        warehouse = db.get(Warehouse, body.warehouse_id)
        if not warehouse or (warehouse.status or "").lower() != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
        warehouse_id = warehouse.id
        store_id = None

    elif user.role == "store_manager":
        if body.warehouse_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please select a warehouse",
            )
        if body.store_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please select a store location",
            )
        store = db.get(Store, body.store_id)
        if not store or (store.status or "").lower() not in ("open", "active"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        if store.warehouse_id is not None and store.warehouse_id != body.warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Selected store does not belong to that warehouse",
            )
        if user.store_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Store manager is not linked to a store",
            )
        if user.store_id != body.store_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="These credentials are not valid for the selected store",
            )
        warehouse = db.get(Warehouse, body.warehouse_id)
        warehouse_id = body.warehouse_id
        store_id = store.id

    else:
        warehouse_id = body.warehouse_id or user.warehouse_id
        store_id = body.store_id or user.store_id
        if warehouse_id:
            warehouse = db.get(Warehouse, warehouse_id)
        if store_id:
            store = db.get(Store, store_id)

    token = create_access_token(
        user.id,
        user.role,
        warehouse_id=warehouse_id,
        store_id=store_id,
    )
    return TokenResponse(
        access_token=token,
        user=_user_out(user, warehouse=warehouse, store=store),
    )
