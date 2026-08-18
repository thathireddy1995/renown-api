"""DTOs for Offer (admin) endpoints."""

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


def aliased(default, snake: str, camel: str, **kwargs):
    return Field(
        default,
        validation_alias=AliasChoices(snake, camel),
        serialization_alias=camel,
        **kwargs,
    )


class OfferOut(BaseModel):
    """Offer response DTO."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    id: int
    name: str
    slug: str
    discount_type: str = aliased(..., "discount_type", "discountType")
    discount_value: Decimal = aliased(..., "discount_value", "discountValue")
    maximum_discount: Decimal | None = aliased(None, "maximum_discount", "maximumDiscount")
    apply_on: str = aliased(..., "apply_on", "applyOn")
    product_id: int | None = aliased(None, "product_id", "productId")
    product_name: str | None = aliased(None, "product_name", "productName")
    brand_id: int | None = aliased(None, "brand_id", "brandId")
    brand_name: str | None = aliased(None, "brand_name", "brandName")
    category_id: int | None = aliased(None, "category_id", "categoryId")
    category_name: str | None = aliased(None, "category_name", "categoryName")
    gender: str | None = None
    start_date: datetime = aliased(..., "start_date", "startDate")
    end_date: datetime = aliased(..., "end_date", "endDate")
    priority: int
    status: str
    created_at: datetime = aliased(..., "created_at", "createdAt")
    updated_at: datetime = aliased(..., "updated_at", "updatedAt")
    created_by: int | None = aliased(None, "created_by", "createdBy")
    updated_by: int | None = aliased(None, "updated_by", "updatedBy")


class OfferCreate(BaseModel):
    """Offer creation DTO."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=200)
    discount_type: str = aliased(
        ..., "discount_type", "discountType", pattern="^(FLAT|PERCENTAGE)$"
    )
    discount_value: Decimal = aliased(
        ..., "discount_value", "discountValue", gt=0
    )
    maximum_discount: Decimal | None = aliased(
        None, "maximum_discount", "maximumDiscount", gt=0
    )
    apply_on: str = aliased(
        ..., "apply_on", "applyOn", pattern="^(PRODUCT|BRAND|CATEGORY|GENDER)$"
    )
    product_id: int | None = aliased(None, "product_id", "productId")
    brand_id: int | None = aliased(None, "brand_id", "brandId")
    category_id: int | None = aliased(None, "category_id", "categoryId")
    gender: str | None = Field(None, pattern="^(MALE|FEMALE|UNISEX|KIDS)?$")
    start_date: datetime = aliased(..., "start_date", "startDate")
    end_date: datetime = aliased(..., "end_date", "endDate")
    priority: int = Field(default=0, ge=0)


class OfferUpdate(BaseModel):
    """Offer update DTO."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(None, min_length=1, max_length=200)
    discount_type: str | None = aliased(
        None, "discount_type", "discountType", pattern="^(FLAT|PERCENTAGE)$"
    )
    discount_value: Decimal | None = aliased(
        None, "discount_value", "discountValue", gt=0
    )
    maximum_discount: Decimal | None = aliased(
        None, "maximum_discount", "maximumDiscount", gt=0
    )
    apply_on: str | None = aliased(
        None, "apply_on", "applyOn", pattern="^(PRODUCT|BRAND|CATEGORY|GENDER)$"
    )
    product_id: int | None = aliased(None, "product_id", "productId")
    brand_id: int | None = aliased(None, "brand_id", "brandId")
    category_id: int | None = aliased(None, "category_id", "categoryId")
    gender: str | None = Field(None, pattern="^(MALE|FEMALE|UNISEX|KIDS)?$")
    start_date: datetime | None = aliased(None, "start_date", "startDate")
    end_date: datetime | None = aliased(None, "end_date", "endDate")
    priority: int | None = Field(None, ge=0)


class OfferListResponse(BaseModel):
    """Paginated offer list response."""

    items: list[OfferOut]
    total: int
    limit: int
    offset: int
