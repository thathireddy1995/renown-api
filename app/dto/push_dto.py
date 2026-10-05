from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PushTokenRegisterRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    platform: str = Field(default="android", max_length=20)


class PushTokenRemoveRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class PushTestRequest(BaseModel):
    audience: Literal["all", "customer", "token"] | None = Field(
        default=None,
        description="Defaults to 'token' when token is set, else 'customer'.",
    )
    token: str | None = Field(default=None, description="Raw FCM device token")
    customer_id: int | None = Field(default=None, description="Send to all of a customer's devices")
    title: str = Field(default="Renown", min_length=1, max_length=120)
    body: str = Field(default="Test notification from the Renown API", min_length=1, max_length=500)
    data: dict[str, str] | None = None
    image: str | None = Field(default=None, max_length=1000, description="Public https image URL")


class PushSendResult(BaseModel):
    sent: int
    failed: int
    removed: int
    errors: list[str] = []


class PushStatsOut(BaseModel):
    devices: int
    customers: int


class PushRecipientOut(BaseModel):
    id: int
    name: str | None
    phone: str | None
    email: str | None
    devices: int


class PushRecipientListResponse(BaseModel):
    items: list[PushRecipientOut]


class PushLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    image_url: str | None
    audience: str
    customer_id: int | None
    customer_name: str | None = None
    sent: int
    failed: int
    created_at: datetime


class PushLogListResponse(BaseModel):
    items: list[PushLogOut]
