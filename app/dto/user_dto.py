"""Admin user-management DTOs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None = None
    email: str
    role: str
    is_active: bool
    store_id: int | None = None
    warehouse_id: int | None = None
    store_name: str | None = None
    warehouse_name: str | None = None
    last_login: datetime | None = None
    created_at: datetime | None = None


class AdminUserCounts(BaseModel):
    total: int = 0
    active: int = 0
    inactive: int = 0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int
    counts: AdminUserCounts = Field(default_factory=AdminUserCounts)


class AdminUserCreate(BaseModel):
    name: str
    phone: str
    password: str
    role: str
    store_id: int | None = None
    warehouse_id: int | None = None
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    store_id: int | None = None
    warehouse_id: int | None = None
    is_active: bool | None = None


class AdminUserPasswordReset(BaseModel):
    password: str
