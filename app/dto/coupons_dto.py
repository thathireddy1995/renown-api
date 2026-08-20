"""DTOs for coupon admin + customer endpoints."""

from datetime import datetime
from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


def aliased(default, snake: str, camel: str, **kwargs):
    return Field(
        default,
        validation_alias=AliasChoices(snake, camel),
        serialization_alias=camel,
        **kwargs,
    )


def _normalize_code(value: str) -> str:
    return "".join(value.strip().upper().split())


class CouponOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    id: int
    name: str
    code: str
    discount_type: str = aliased(..., "discount_type", "discountType")
    discount_value: Decimal = aliased(..., "discount_value", "discountValue")
    maximum_discount: Decimal | None = aliased(None, "maximum_discount", "maximumDiscount")
    min_order_amount: Decimal = aliased(Decimal("0"), "min_order_amount", "minOrderAmount")
    apply_on: str = aliased(..., "apply_on", "applyOn")
    brand_id: int | None = aliased(None, "brand_id", "brandId")
    brand_name: str | None = aliased(None, "brand_name", "brandName")
    category_id: int | None = aliased(None, "category_id", "categoryId")
    category_name: str | None = aliased(None, "category_name", "categoryName")
    gender: str | None = None
    start_date: datetime = aliased(..., "start_date", "startDate")
    end_date: datetime = aliased(..., "end_date", "endDate")
    usage_limit: int | None = aliased(None, "usage_limit", "usageLimit")
    per_customer_limit: int | None = aliased(None, "per_customer_limit", "perCustomerLimit")
    used_count: int = aliased(0, "used_count", "usedCount")
    status: str
    created_at: datetime = aliased(..., "created_at", "createdAt")
    updated_at: datetime = aliased(..., "updated_at", "updatedAt")


class CouponCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=3, max_length=30)
    discount_type: str = aliased(
        ..., "discount_type", "discountType", pattern="^(FLAT|PERCENTAGE)$"
    )
    discount_value: Decimal = aliased(..., "discount_value", "discountValue", gt=0)
    maximum_discount: Decimal | None = aliased(
        None, "maximum_discount", "maximumDiscount", gt=0
    )
    min_order_amount: Decimal = aliased(
        Decimal("0"), "min_order_amount", "minOrderAmount", ge=0
    )
    apply_on: str = aliased(
        "ALL", "apply_on", "applyOn", pattern="^(ALL|BRAND|CATEGORY|GENDER)$"
    )
    brand_id: int | None = aliased(None, "brand_id", "brandId")
    category_id: int | None = aliased(None, "category_id", "categoryId")
    gender: str | None = Field(None, pattern="^(MALE|FEMALE|UNISEX|KIDS)?$")
    start_date: datetime = aliased(..., "start_date", "startDate")
    end_date: datetime = aliased(..., "end_date", "endDate")
    usage_limit: int | None = aliased(None, "usage_limit", "usageLimit", gt=0)
    per_customer_limit: int | None = aliased(
        1, "per_customer_limit", "perCustomerLimit", gt=0
    )

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        code = _normalize_code(str(value or ""))
        if not code:
            raise ValueError("Coupon code is required.")
        if not all(ch.isalnum() or ch in "-_" for ch in code):
            raise ValueError("Coupon code may only contain letters, numbers, hyphen, or underscore.")
        return code

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return str(value or "").strip()


class CouponUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(None, min_length=1, max_length=200)
    code: str | None = Field(None, min_length=3, max_length=30)
    discount_type: str | None = aliased(
        None, "discount_type", "discountType", pattern="^(FLAT|PERCENTAGE)$"
    )
    discount_value: Decimal | None = aliased(None, "discount_value", "discountValue", gt=0)
    maximum_discount: Decimal | None = aliased(
        None, "maximum_discount", "maximumDiscount", gt=0
    )
    min_order_amount: Decimal | None = aliased(
        None, "min_order_amount", "minOrderAmount", ge=0
    )
    apply_on: str | None = aliased(
        None, "apply_on", "applyOn", pattern="^(ALL|BRAND|CATEGORY|GENDER)$"
    )
    brand_id: int | None = aliased(None, "brand_id", "brandId")
    category_id: int | None = aliased(None, "category_id", "categoryId")
    gender: str | None = Field(None, pattern="^(MALE|FEMALE|UNISEX|KIDS)?$")
    start_date: datetime | None = aliased(None, "start_date", "startDate")
    end_date: datetime | None = aliased(None, "end_date", "endDate")
    usage_limit: int | None = aliased(None, "usage_limit", "usageLimit", gt=0)
    per_customer_limit: int | None = aliased(
        None, "per_customer_limit", "perCustomerLimit", gt=0
    )

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = _normalize_code(str(value))
        if not code:
            return None
        if not all(ch.isalnum() or ch in "-_" for ch in code):
            raise ValueError("Coupon code may only contain letters, numbers, hyphen, or underscore.")
        return code

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip()


class CouponListResponse(BaseModel):
    items: list[CouponOut]
    total: int
    limit: int
    offset: int


class CouponValidateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return _normalize_code(str(value or ""))


class CouponValidateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    code: str
    name: str
    discount: Decimal
    discount_type: str = aliased(..., "discount_type", "discountType")
    discount_value: Decimal = aliased(..., "discount_value", "discountValue")
    label: str
    eligible_subtotal: Decimal = aliased(..., "eligible_subtotal", "eligibleSubtotal")
