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
