"""Store manager tablet app DTOs — /store/app."""

from pydantic import BaseModel, Field

from app.dto.prescription_dto import CustomerPrescriptionOut


class StoreAppLocationOut(BaseModel):
    kind: str = "store"
    id: int
    code: str
    name: str
    address: str = ""
    city: str = ""
    country: str = ""
    phone: str = ""


class StoreAppMeOut(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    role: str
    location: StoreAppLocationOut


class StoreAppHomeOut(BaseModel):
    open_orders: int = 0
    pickups_today: int = 0
    low_stock: int = 0
    sku_count: int = 0
    pickups: list["StoreAppOrderOut"] = Field(default_factory=list)
    stock_alerts: list["StoreAppStockOut"] = Field(default_factory=list)
    location: StoreAppLocationOut | None = None


class StoreAppStockOut(BaseModel):
    id: str
    variant_id: int
    name: str
    sku: str
    product_id: str = ""
    category: str
    count: int
    price: float
    low: bool = False
    serials: list[str] = Field(default_factory=list)


class StoreAppStockListOut(BaseModel):
    items: list[StoreAppStockOut]
    total: int
    limit: int
    offset: int
    store_id: int
    store_name: str = ""


class StoreAppOrderOut(BaseModel):
    id: str
    db_id: int
    customer_name: str
    customer_phone: str
    frame_name: str
    lens_type: str = ""
    power: str = ""
    status: str
    fulfillment: str
    payment: str
    amount: float
    created_at: str
    pickup_at: str | None = None
    serial: str | None = None
    lens_fit: dict | None = None


class StoreAppOrderListOut(BaseModel):
    items: list[StoreAppOrderOut]
    total: int
    limit: int
    offset: int


class StoreAppCustomerOut(BaseModel):
    phone: str
    name: str
    email: str | None = None
    power_summary: str = ""
    saved_rx: str | None = None
    past_order_count: int = 0
    prescription: CustomerPrescriptionOut | None = None


class StoreAppOtpRequest(BaseModel):
    phone: str


class StoreAppOtpVerify(BaseModel):
    phone: str
    otp: str


class StoreAppOtpResponse(BaseModel):
    message: str
    expires_in_seconds: int = 300
    debug_otp: str | None = None


class StoreAppEyeRx(BaseModel):
    sph: str = ""
    cyl: str = ""
    axis: str = ""
    pd: str = ""
    add: str = ""


class StoreAppPlaceOrderRequest(BaseModel):
    customer_phone: str
    variant_id: int
    lens_type: str = ""
    power: str = ""
    fulfillment: str = "store_pickup"
    payment: str = "cod"
    amount: float | None = None
    power_mode: str = "powered"
    vision_type: str = "single_vision"
    prescription: dict | None = None  # { right: EyeRx, left: EyeRx }


class StoreAppStatusPatch(BaseModel):
    status: str
    otp: str | None = None
