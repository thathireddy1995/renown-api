from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.dto.auth_dto import StaffLoginRequest, TokenResponse, UserOut
from app.schemas import Store, User, Warehouse

router = APIRouter(prefix="/staff/auth", tags=["staff-auth"])

MANAGER_ROLES = ("store_manager", "warehouse_manager")


@router.post("/login", response_model=TokenResponse)
def login(payload: StaffLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    phone = "".join(ch for ch in payload.phone if ch.isdigit())

    user = db.scalar(
        select(User).where(
            User.phone == phone,
            User.role.in_(MANAGER_ROLES),
            User.is_active.is_(True),
        )
    )

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid phone number or password.",
        )

    store_id = None
    warehouse_id = None
    if user.role == "store_manager":
        store = db.scalar(
            select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
        ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))
        store_id = store.id if store else None
    elif user.role == "warehouse_manager":
        wh = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
        warehouse_id = wh.id if wh else None

    token = create_access_token(
        user.id, user.role, store_id=store_id, warehouse_id=warehouse_id
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))
