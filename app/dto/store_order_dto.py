"""Store order / POS DTOs."""

from pydantic import BaseModel, Field


class PosCatalogItemOut(BaseModel):
    id: str
    name: str
    sku: str
    price: float
    category: str
    stock: int = 0
    variant_id: int


class PosCatalogResponse(BaseModel):
    items: list[PosCatalogItemOut]
    store_id: int
    store_name: str = ""


class PosCheckoutLine(BaseModel):
    variant_id: int
    qty: int = 1


class PosCheckoutRequest(BaseModel):
    store_id: int | None = None
    customer_name: str | None = None
    payment_method: str = "card"
    associate_name: str | None = None
    items: list[PosCheckoutLine] = Field(default_factory=list)


class PosCheckoutOut(BaseModel):
    id: str
    total: float
    subtotal: float
    tax: float
    status: str
    message: str = ""


class StoreOrderOut(BaseModel):
    """Admin store-orders row shape."""

    id: str
    store: str
    customer: str
    items: int
    total: float
    payment: str
    associate: str
    time: str
    status: str
    type: str


class StaffStoreOrderOut(BaseModel):
    id: str
    customer: str
    items: int
    channel: str
    total: str
    status: str
    date: str


class StoreOrderListResponse(BaseModel):
    items: list[StoreOrderOut]
    total: int
    limit: int
    offset: int
    counts: dict[str, int] = Field(default_factory=dict)


class StaffStoreOrderListResponse(BaseModel):
    items: list[StaffStoreOrderOut]
    total: int
    limit: int
    offset: int


class StoreAnalyticsKpis(BaseModel):
    revenueToday: float = 0
    ordersToday: int = 0
    avgBasket: float = 0
    salesPerAssociate: float = 0


class StoreAnalyticsTrendPoint(BaseModel):
    day: str
    revenue: float
    orders: int = 0
    footfall: int = 0


class StoreAnalyticsMixPoint(BaseModel):
    store: str
    revenue: float


class StoreAnalyticsResponse(BaseModel):
    kpis: StoreAnalyticsKpis
    trend: list[StoreAnalyticsTrendPoint]
    revenueMix: list[StoreAnalyticsMixPoint]
