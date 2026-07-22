"""Shared FastAPI dependencies (pagination, auth)."""

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import TokenPrincipal, require_role
from app.core.security import decode_access_token
from app.database import get_db
from app.schemas import Customer, User

_bearer = HTTPBearer(auto_error=False)

STAFF_ROLES = frozenset({"store_manager", "warehouse_manager", "admin"})
WAREHOUSE_ROLES = frozenset({"warehouse_manager", "admin"})
STORE_ROLES = frozenset({"store_manager", "admin"})

__all__ = [
    "TokenPrincipal",
    "require_role",
    "pagination",
    "get_current_customer",
    "get_current_staff",
    "get_current_warehouse_staff",
    "get_current_store_staff",
    "STAFF_ROLES",
    "WAREHOUSE_ROLES",
    "STORE_ROLES",
]


def pagination(
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> tuple[int, int]:
    return limit, offset


def get_current_customer(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Customer:
    if not creds or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    try:
        payload = decode_access_token(creds.credentials)
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )

    if payload.get("role") != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer access required.",
        )

    try:
        customer_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
        )

    customer = db.scalar(
        select(Customer).where(Customer.id == customer_id, Customer.is_active.is_(True))
    )
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer not found.",
        )
    return customer


def get_current_staff(
    principal: TokenPrincipal = Depends(require_role("store_manager", "warehouse_manager", "admin")),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(
        select(User).where(User.id == principal.sub, User.is_active.is_(True))
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff user not found.",
        )
    return user


def get_current_warehouse_staff(
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(
        select(User).where(User.id == principal.sub, User.is_active.is_(True))
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff user not found.",
        )
    return user


def get_current_store_staff(
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    db: Session = Depends(get_db),
) -> User:
    user = db.scalar(
        select(User).where(User.id == principal.sub, User.is_active.is_(True))
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff user not found.",
        )
    return user
