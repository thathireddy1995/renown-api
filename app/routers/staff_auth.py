from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.dto.auth_dto import StaffLoginRequest, TokenResponse, UserOut
from app.schemas import User

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

    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))
