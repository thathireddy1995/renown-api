from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.core.staff_users import stamp_last_login
from app.database import get_db
from app.deps import require_role, TokenPrincipal
from app.dto.auth_dto import (
    AdminChangePasswordRequest,
    AdminLoginRequest,
    TokenResponse,
    UserOut,
)
from app.schemas import User

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    phone = "".join(ch for ch in payload.mobile if ch.isdigit())

    user = db.scalar(
        select(User).where(
            User.phone == phone,
            User.role == "admin",
            User.is_active.is_(True),
        )
    )

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid mobile number or password.",
        )

    token = create_access_token(user.id, user.role)
    user_out = UserOut.model_validate(user)
    stamp_last_login(db, user)
    return TokenResponse(access_token=token, user=user_out)


@router.post("/change-password")
def change_password(
    payload: AdminChangePasswordRequest,
    principal: TokenPrincipal = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = db.get(User, principal.sub)
    if not user or user.role != "admin" or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found.",
        )
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if payload.current_password == payload.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current password.",
        )
    if len(payload.new_password) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 4 characters.",
        )
    user.password_hash = hash_password(payload.new_password)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"status": "ok"}
