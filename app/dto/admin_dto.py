"""Admin portal request/response DTOs — orders & customers."""

from pydantic import BaseModel, ConfigDict, Field


class AdminOrderOut(BaseModel):
    """List row matching admin.orders.tsx columns."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    customer: str
    date: str
    items: int
    status: str
    total: float


class AdminOrderItemOut(BaseModel):
    productId: str
    name: str
    qty: int
    price: float


class AdminOrderDetailOut(AdminOrderOut):
    db_id: int
    customer_id: int
    customer_email: str | None = None
    customer_phone: str | None = None
    subtotal: float = 0
    discount: float = 0
    shipping: float = 0
    tax: float = 0
    coupon_code: str | None = None
    line_items: list[AdminOrderItemOut] = Field(default_factory=list)


class AdminOrderListResponse(BaseModel):
    items: list[AdminOrderOut]
    total: int
    limit: int
    offset: int


class AdminOrderStatusUpdate(BaseModel):
    status: str


class AdminCustomerOut(BaseModel):
    """List row matching admin.customers.tsx columns."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    email: str
    orders: int
    spent: float
    lastOrder: str = ""


class AdminCustomerDetailOut(AdminCustomerOut):
    phone: str | None = None
    is_active: bool = True
    created_at: str = ""
    recent_orders: list[AdminOrderOut] = Field(default_factory=list)


class AdminCustomerListResponse(BaseModel):
    items: list[AdminCustomerOut]
    total: int
    limit: int
    offset: int


class AdminStockTransferOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, ser_json_by_alias=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    sku: str
    qty: int
    status: str
    eta: str = "—"
    created: str = ""


class AdminStockTransferItemIn(BaseModel):
    variant_id: int
    qty: int


class AdminStockTransferCreate(BaseModel):
    from_warehouse_id: int
    to_warehouse_id: int | None = None
    to_store_id: int | None = None
    requested_by: str | None = None
    eta: str | None = None
    status: str = "requested"
    items: list[AdminStockTransferItemIn] = Field(default_factory=list)


class AdminStockTransferStatusUpdate(BaseModel):
    status: str


class AdminStockTransferListResponse(BaseModel):
    items: list[AdminStockTransferOut]
    total: int
    limit: int
    offset: int
    counts: dict[str, int] = Field(default_factory=dict)


class AdminTransferRequestOut(BaseModel):
    id: str
    requester: str
    target: str
    sku: str
    qty: int
    urgency: str
    date: str
    status: str


class AdminTransferRequestCreate(BaseModel):
    requester_warehouse_id: int
    target_warehouse_id: int
    variant_id: int
    qty: int
    urgency: str = "Medium"


class AdminTransferRequestListResponse(BaseModel):
    items: list[AdminTransferRequestOut]
    total: int
    limit: int
    offset: int


class AdminStockAllocationOut(BaseModel):
    id: str
    order: str
    sku: str
    qty: int
    warehouse: str
    picker: str = "—"
    created: str = ""
    status: str


class AdminStockAllocationListResponse(BaseModel):
    items: list[AdminStockAllocationOut]
    total: int
    limit: int
    offset: int
    counts: dict[str, int] = Field(default_factory=dict)
