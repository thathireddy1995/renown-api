"""DTOs for Offer (admin) endpoints."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OfferOut(BaseModel):
    """Offer response DTO."""

    id: int
    name: str
    slug: str
    discountType: str = Field(alias="discount_type")
    discountValue: Decimal = Field(alias="discount_value")
    maximumDiscount: Decimal | None = Field(alias="maximum_discount")
    applyOn: str = Field(alias="apply_on")
    productId: int | None = Field(alias="product_id")
    productName: str | None = Field(None, alias="product_name")
    brandId: int | None = Field(alias="brand_id")
    brandName: str | None = Field(None, alias="brand_name")
    categoryId: int | None = Field(alias="category_id")
    categoryName: str | None = Field(None, alias="category_name")
    gender: str | None = None
    startDate: datetime = Field(alias="start_date")
    endDate: datetime = Field(alias="end_date")
    priority: int
    status: str
    createdAt: datetime = Field(alias="created_at")
    updatedAt: datetime = Field(alias="updated_at")

    class Config:
        populate_by_name = True


class OfferCreate(BaseModel):
    """Offer creation DTO."""

    name: str = Field(..., min_length=1, max_length=200)
    discountType: str = Field(
        ..., alias="discount_type", pattern="^(FLAT|PERCENTAGE)$"
    )
    discountValue: Decimal = Field(..., alias="discount_value", gt=0)
    maximumDiscount: Decimal | None = Field(None, alias="maximum_discount", gt=0)
    applyOn: str = Field(
        ..., alias="apply_on", pattern="^(PRODUCT|BRAND|CATEGORY|GENDER)$"
    )
    productId: int | None = Field(None, alias="product_id")
    brandId: int | None = Field(None, alias="brand_id")
    categoryId: int | None = Field(None, alias="category_id")
    gender: str | None = Field(None, pattern="^(MALE|FEMALE|UNISEX)?$")
    startDate: datetime = Field(..., alias="start_date")
    endDate: datetime = Field(..., alias="end_date")
    priority: int = Field(default=0, ge=0)

    class Config:
        populate_by_name = True


class OfferUpdate(BaseModel):
    """Offer update DTO."""

    name: str | None = Field(None, min_length=1, max_length=200)
    discountType: str | None = Field(
        None, alias="discount_type", pattern="^(FLAT|PERCENTAGE)$"
    )
    discountValue: Decimal | None = Field(None, alias="discount_value", gt=0)
    maximumDiscount: Decimal | None = Field(None, alias="maximum_discount", gt=0)
    applyOn: str | None = Field(
        None, alias="apply_on", pattern="^(PRODUCT|BRAND|CATEGORY|GENDER)$"
    )
    productId: int | None = Field(None, alias="product_id")
    brandId: int | None = Field(None, alias="brand_id")
    categoryId: int | None = Field(None, alias="category_id")
    gender: str | None = Field(None, pattern="^(MALE|FEMALE|UNISEX)?$")
    startDate: datetime | None = Field(None, alias="start_date")
    endDate: datetime | None = Field(None, alias="end_date")
    priority: int | None = Field(None, ge=0)

    class Config:
        populate_by_name = True


class OfferListResponse(BaseModel):
    """Paginated offer list response."""

    items: list[OfferOut]
    total: int
    limit: int
    offset: int
