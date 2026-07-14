"""Employee directory DTOs."""

from pydantic import BaseModel


class AdminEmployeeOut(BaseModel):
    id: str
    name: str
    role: str
    type: str  # store | warehouse
    location: str
    shift: str
    status: str


class AdminEmployeeListResponse(BaseModel):
    items: list[AdminEmployeeOut]
    total: int
    limit: int
    offset: int


class AdminEmployeeCreate(BaseModel):
    employee_code: str | None = None
    name: str
    role: str
    type: str = "store"
    location: str | None = None
    store_id: int | None = None
    warehouse_id: int | None = None
    shift: str = "Day"
    status: str = "On duty"
    phone: str | None = None
    mtd_sales: float = 0


class AdminEmployeeUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    type: str | None = None
    location: str | None = None
    store_id: int | None = None
    warehouse_id: int | None = None
    shift: str | None = None
    status: str | None = None
    phone: str | None = None
    mtd_sales: float | None = None


class StaffEmployeeOut(BaseModel):
    id: str
    name: str
    role: str
    phone: str
    shift: str
    sales: str
    status: str


class StaffEmployeeListResponse(BaseModel):
    items: list[StaffEmployeeOut]
    total: int
    limit: int
    offset: int


class StaffEmployeeCreate(BaseModel):
    name: str
    role: str
    phone: str | None = None
    shift: str = "Day"
    status: str = "Active"
    employee_code: str | None = None
    store_id: int | None = None


class StaffEmployeeStatusUpdate(BaseModel):
    status: str
