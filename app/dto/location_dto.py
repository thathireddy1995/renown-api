"""Admin location / inventory DTOs matching admin-renown UI field names."""

from pydantic import BaseModel, ConfigDict, Field


class WarehouseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    city: str = ""
    country: str = ""
    manager: str = ""
    capacity: int = 0
    used: int = 0
    skus: int = 0
    staff: int = 0
    status: str = "Active"


class WarehouseCreate(BaseModel):
    code: str
    name: str
    city: str | None = None
    country: str | None = None
    manager: str | None = None
    capacity: int = 0
    staff: int = 0
    status: str = "Active"


class WarehouseUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    city: str | None = None
    country: str | None = None
    manager: str | None = None
    capacity: int | None = None
    staff: int | None = None
    status: str | None = None


class WarehouseListResponse(BaseModel):
    items: list[WarehouseOut]
    total: int
    limit: int
    offset: int


class WhInventoryOut(BaseModel):
    """Matches admin.warehouse-inventory.tsx row shape."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    sku: str
    product: str
    warehouse: str
    bin: str = ""
    onHand: int = 0
    reserved: int = 0
    reorder: int = 0
    status: str


class WhInventoryListResponse(BaseModel):
    items: list[WhInventoryOut]
    total: int
    limit: int
    offset: int


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    code: str
    name: str
    city: str = ""
    country: str = ""
    address: str = ""
    manager: str = ""
    phone: str = ""
    hours: str = ""
    staff: int = 0
    skus: int = 0
    status: str = "Open"
    todayRevenue: float = 0
    todayOrders: int = 0


class StoreCreate(BaseModel):
    code: str
    name: str
    address: str | None = None
    city: str | None = None
    country: str | None = None
    phone: str | None = None
    hours: str | None = None
    manager: str | None = None
    staff: int = 0
    status: str = "Open"
    today_revenue: float = 0
    today_orders: int = 0


class StoreUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    phone: str | None = None
    hours: str | None = None
    manager: str | None = None
    staff: int | None = None
    status: str | None = None
    today_revenue: float | None = None
    today_orders: int | None = None


class StoreListResponse(BaseModel):
    items: list[StoreOut]
    total: int
    limit: int
    offset: int


class StoreInventoryOut(BaseModel):
    """Matches admin.store-inventory.tsx row shape."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    store: str
    sku: str
    product: str
    onFloor: int = 0
    backroom: int = 0
    reserved: int = 0
    reorder: int = 0
    status: str


class StoreInventoryListResponse(BaseModel):
    items: list[StoreInventoryOut]
    total: int
    limit: int
    offset: int


class AdminInventoryAuditOut(BaseModel):
    id: str
    warehouse: str
    scope: str
    scanned: int
    expected: int
    variance: int
    status: str
    date: str


class AdminInventoryAuditListResponse(BaseModel):
    items: list[AdminInventoryAuditOut]
    total: int
    limit: int
    offset: int
