"""JWT role gate — no DB lookup; role claim is enough."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError

from app.core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TokenPrincipal:
    sub: int
    role: str
    store_id: int | None = None
    warehouse_id: int | None = None


def require_role(*roles: str):
    """FastAPI dependency factory: 401 if missing/invalid token, 403 if wrong role."""
    allowed = frozenset(roles)

    def _dependency(
        creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> TokenPrincipal:
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

        role = payload.get("role")
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )

        try:
            sub = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject.",
            )

        store_id = payload.get("store_id")
        warehouse_id = payload.get("warehouse_id")
        try:
            store_id = int(store_id) if store_id is not None else None
        except (TypeError, ValueError):
            store_id = None
        try:
            warehouse_id = int(warehouse_id) if warehouse_id is not None else None
        except (TypeError, ValueError):
            warehouse_id = None

        return TokenPrincipal(
            sub=sub, role=str(role), store_id=store_id, warehouse_id=warehouse_id
        )

    return _dependency
