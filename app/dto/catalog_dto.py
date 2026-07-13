from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    sort_order: int = 0


class ProductImageCreate(BaseModel):
    url: str
    sort_order: int = 0


class ProductVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    product: str = ""
    sku: str
    color: str | None = None
    color_hex: str | None = None
    size: str | None = None
    price: Decimal | None = None
    stock: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductVariantCreate(BaseModel):
    product_id: int | None = None
    sku: str = Field(max_length=40)
    color: str | None = None
    color_hex: str | None = None
    size: str | None = None
    price: Decimal | None = None
    stock: int = 0


class ProductVariantUpdate(BaseModel):
    product_id: int | None = None
    sku: str | None = Field(default=None, max_length=40)
    color: str | None = None
    color_hex: str | None = None
    size: str | None = None
    price: Decimal | None = None
    stock: int | None = None


class ProductOut(BaseModel):
    """Admin + customer product shape. Extra storefront fields are filled
    from variants/images (or sensible defaults) so existing UIs keep working."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    db_id: int
    name: str
    slug: str
    sku: str
    description: str | None = None
    price: float
    compare_at_price: float | None = None
    compareAt: float | None = None
    brand: str = ""
    brand_id: int | None = None
    category: str = ""
    category_id: int | None = None
    gender: str | None = None
    shape: str | None = None
    material: str | None = None
    rim_type: str | None = None
    rimType: str | None = None
    warranty: str | None = None
    is_new: bool = False
    isNew: bool = False
    is_bestseller: bool = False
    isBestSeller: bool = False
    isBestseller: bool = False
    is_trending: bool = False
    isTrending: bool = False
    status: str = "draft"
    image: str = ""
    images: list[str] = Field(default_factory=list)
    variants: list[ProductVariantOut] = Field(default_factory=list)
    stock: int = 0
    inStock: bool = False
    color: str = ""
    colorHex: str = ""
    size: str = ""
    lensType: str = ""
    weight: str = ""
    rating: float = 4.5
    reviews: int = 0
    tags: list[str] = Field(default_factory=list)
    offer: str | None = None
    originalPrice: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductCreate(BaseModel):
    name: str = Field(max_length=200)
    slug: str | None = Field(default=None, max_length=220)
    sku: str = Field(max_length=40)
    description: str | None = None
    price: Decimal
    compare_at_price: Decimal | None = None
    brand: str | None = None
    brand_id: int | None = None
    category: str | None = None
    category_id: int | None = None
    gender: str | None = None
    shape: str | None = None
    material: str | None = None
    rim_type: str | None = None
    warranty: str | None = None
    is_new: bool = False
    is_bestseller: bool = False
    is_trending: bool = False
    status: str = "draft"
    images: list[ProductImageCreate] = Field(default_factory=list)
    variants: list[ProductVariantCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=220)
    sku: str | None = Field(default=None, max_length=40)
    description: str | None = None
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    brand: str | None = None
    brand_id: int | None = None
    category: str | None = None
    category_id: int | None = None
    gender: str | None = None
    shape: str | None = None
    material: str | None = None
    rim_type: str | None = None
    warranty: str | None = None
    is_new: bool | None = None
    is_bestseller: bool | None = None
    is_trending: bool | None = None
    status: str | None = None
    images: list[ProductImageCreate] | None = None


class ProductListResponse(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int


class VariantListResponse(BaseModel):
    items: list[ProductVariantOut]
    total: int
    limit: int
    offset: int
