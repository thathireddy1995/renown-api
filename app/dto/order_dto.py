from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AddressOut(BaseModel):
    """UI-shaped address row used by checkout + account."""

    id: str
    name: str
    line1: str
    line2: str | None = None
    city: str = ""
    zip: str = ""
    phone: str = ""
    state: str | None = None
    country: str | None = None
    is_default: bool = False


class AddressCreate(BaseModel):
    name: str | None = Field(default=None, max_length=40)  # label
    label: str | None = Field(default=None, max_length=40)
    line1: str = Field(max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    zip: str | None = Field(default=None, max_length=20)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    is_default: bool = False


class AddressUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    label: str | None = Field(default=None, max_length=40)
    line1: str | None = Field(default=None, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=80)
    state: str | None = Field(default=None, max_length=80)
    zip: str | None = Field(default=None, max_length=20)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    is_default: bool | None = None


class AddressListResponse(BaseModel):
    items: list[AddressOut]


class OrderItemOut(BaseModel):
    productId: str
    name: str
    qty: int
    price: float
    compare_at: float | None = None
    brand: str | None = None
    category: str | None = None
    sku: str | None = None
    variant_sku: str | None = None
    color: str | None = None
    color_hex: str | None = None
    size: str | None = None
    frame_type: str | None = None
    shape: str | None = None
    material: str | None = None
    gender: str | None = None
    warranty: str | None = None
    description: str | None = None
    image: str | None = None


class PickupStoreOut(BaseModel):
    id: int
    name: str
    city: str = ""
    address: str = ""
    phone: str = ""


class OrderOut(BaseModel):
    """Matches account/track-order store Order shape (+ extras)."""

    id: str  # order_number
    date: str
    status: str
    total: float
    subtotal: float = 0
    discount: float = 0
    shipping: float = 0
    tax: float = 0
    coupon_code: str | None = None
    payment_method: str = "cod"  # cod | razorpay
    payment_status: str = "pending"  # pending | paid | failed
    delivery: str = "ship"  # ship | pickup
    address: AddressOut | None = None
    pickup_store: PickupStoreOut | None = None
    awb_code: str | None = None
    courier_name: str | None = None
    tracking_url: str | None = None
    items: list[OrderItemOut] = Field(default_factory=list)


class TrackingActivityOut(BaseModel):
    date: str = ""
    activity: str = ""
    location: str = ""


class OrderTrackingOut(BaseModel):
    order_id: str
    status: str
    awb_code: str | None = None
    courier_name: str | None = None
    tracking_url: str | None = None
    current_status: str | None = None
    edd: str | None = None
    origin: str | None = None
    destination: str | None = None
    activities: list[TrackingActivityOut] = Field(default_factory=list)
    shiprocket: bool = False
    message: str | None = None


class OrderCreateRequest(BaseModel):
    address_id: int | None = None
    delivery: str = "ship"  # ship | pickup
    pickup_store_id: int | None = None
    coupon_code: str | None = None
    notes: str | None = None


class OrderListResponse(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int
