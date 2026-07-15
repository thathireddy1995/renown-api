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
    items: list[OrderItemOut] = Field(default_factory=list)


class OrderCreateRequest(BaseModel):
    address_id: int | None = None
    delivery: str = "ship"  # ship | pickup
    coupon_code: str | None = None
    notes: str | None = None


class OrderListResponse(BaseModel):
    items: list[OrderOut]
    total: int
    limit: int
    offset: int
