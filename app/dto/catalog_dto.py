from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.s3_images import is_view_360_key, public_url_for


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _stored_image_url(value: str) -> str:
    url = value.strip()
    if url.lower().startswith("data:image/"):
        raise ValueError("Inline images are not allowed. Upload the image to S3 first.")
    if not url.lower().startswith(("https://", "http://")):
        raise ValueError("Image must be an HTTP(S) URL.")
    return url


def _stored_image_urls(values: list[str]) -> list[str]:
    return [_stored_image_url(value) for value in values]


def _normalize_view_360(url: str | None, key: str | None) -> tuple[str | None, str | None]:
    url = (url or "").strip() or None
    key = (key or "").strip() or None
    if url is None and key is None:
        return None, None
    if url is None or key is None:
        raise ValueError("360 view URL and storage key must be set together.")
    if not is_view_360_key(key):
        raise ValueError("360 view must be stored under catalog/products/…/360/ as an MP4.")
    if url != public_url_for(key):
        raise ValueError("360 view URL does not match its S3 object key.")
    return url, key


class ProductImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    sort_order: int = 0


class ProductImageCreate(BaseModel):
    url: str
    sort_order: int = 0

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _stored_image_url(value)


class ImagePresignFile(BaseModel):
    filename: str = Field(default="image.jpg", max_length=200)
    content_type: str = Field(default="image/jpeg", max_length=80)


class ImagePresignRequest(BaseModel):
    files: list[ImagePresignFile] = Field(min_length=1, max_length=25)


class ImagePresignItem(BaseModel):
    key: str
    put_url: str
    public_url: str
    content_type: str


class ImagePresignResponse(BaseModel):
    bucket: str
    uploads: list[ImagePresignItem]


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
    images: list[str] = Field(default_factory=list)
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
    images: list[str] = Field(default_factory=list)

    @field_validator("images")
    @classmethod
    def validate_images(cls, values: list[str]) -> list[str]:
        return _stored_image_urls(values)


class ProductVariantUpdate(BaseModel):
    product_id: int | None = None
    sku: str | None = Field(default=None, max_length=40)
    color: str | None = None
    color_hex: str | None = None
    size: str | None = None
    price: Decimal | None = None
    stock: int | None = None
    images: list[str] | None = None

    @field_validator("images")
    @classmethod
    def validate_images(cls, values: list[str] | None) -> list[str] | None:
        return _stored_image_urls(values) if values is not None else None


class ProductOut(BaseModel):
    """Admin + customer product shape. Extra storefront fields are filled
    from variants/images (or sensible defaults) so existing UIs keep working."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    db_id: int
    name: str
    slug: str
    sku: str
    product_id: str | None = None
    productId: str | None = None
    description: str | None = None
    price: float
    compare_at_price: float | None = None
    compareAt: float | None = None
    # Three-tier pricing
    buying_price: float | None = None
    buyingPrice: float | None = None
    mrp: float | None = None
    selling_price: float | None = None
    sellingPrice: float | None = None
    base_selling_price: float | None = None
    baseSellingPrice: float | None = None
    offer_price: float | None = None
    offerPrice: float | None = None
    offer_discount: float = 0
    offerDiscount: float = 0
    applied_offer_id: int | None = None
    appliedOfferId: int | None = None
    applied_offer_name: str | None = None
    appliedOfferName: str | None = None
    discount_percentage: int = 0
    discountPercentage: int = 0
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
    view_360_url: str | None = None
    view360Url: str | None = None
    view_360_key: str | None = None
    view360Key: str | None = None
    variants: list[ProductVariantOut] = Field(default_factory=list)
    stock: int = 0
    inStock: bool = False
    color: str = ""
    colorHex: str = ""
    size: str = ""
    lensType: str = ""
    weight: str = ""
    rating: float = 0
    reviews: int = 0
    tags: list[str] = Field(default_factory=list)
    offer: str | None = None
    originalPrice: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProductCreate(BaseModel):
    name: str = Field(max_length=200)
    slug: str | None = Field(default=None, max_length=220)
    sku: str | None = Field(default=None, max_length=40)
    product_id: str | None = Field(default=None, max_length=40)
    description: str | None = None
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    buying_price: Decimal = Decimal("0")
    mrp: Decimal | None = None
    selling_price: Decimal | None = None
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
    view_360_url: str | None = None
    view_360_key: str | None = None
    variants: list[ProductVariantCreate] = Field(default_factory=list)

    @field_validator("product_id", mode="before")
    @classmethod
    def normalize_product_id(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def validate_prices(self) -> "ProductCreate":
        selling_price = self.selling_price if self.selling_price is not None else self.price
        if selling_price is None or selling_price <= 0:
            raise ValueError("Selling price must be greater than zero.")
        if self.buying_price < 0:
            raise ValueError("Buying price cannot be negative.")
        mrp = self.mrp if self.mrp is not None else self.compare_at_price
        if mrp is not None and mrp <= 0:
            raise ValueError("MRP must be greater than zero.")
        if mrp is not None and selling_price > mrp:
            raise ValueError("Selling price cannot exceed MRP.")
        self.price = selling_price
        self.selling_price = selling_price
        self.mrp = mrp
        self.compare_at_price = mrp
        self.view_360_url, self.view_360_key = _normalize_view_360(
            self.view_360_url, self.view_360_key
        )
        return self


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=220)
    sku: str | None = Field(default=None, max_length=40)
    product_id: str | None = Field(default=None, max_length=40)
    description: str | None = None
    price: Decimal | None = None
    compare_at_price: Decimal | None = None
    # Three-tier pricing (new)
    buying_price: Decimal | None = None
    mrp: Decimal | None = None
    selling_price: Decimal | None = None
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
    view_360_url: str | None = None
    view_360_key: str | None = None

    @field_validator("product_id", mode="before")
    @classmethod
    def normalize_product_id(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def validate_prices(self) -> "ProductUpdate":
        if self.buying_price is not None and self.buying_price < 0:
            raise ValueError("Buying price cannot be negative.")
        selling_price = self.selling_price if self.selling_price is not None else self.price
        if selling_price is not None and selling_price <= 0:
            raise ValueError("Selling price must be greater than zero.")
        mrp = self.mrp if self.mrp is not None else self.compare_at_price
        if mrp is not None and mrp <= 0:
            raise ValueError("MRP must be greater than zero.")
        if selling_price is not None:
            self.price = selling_price
            self.selling_price = selling_price
        if self.mrp is not None or self.compare_at_price is not None:
            self.mrp = mrp
            self.compare_at_price = mrp
        view_fields = {"view_360_url", "view_360_key"} & self.model_fields_set
        if view_fields:
            if len(view_fields) == 1:
                provided = next(iter(view_fields))
                if getattr(self, provided) is not None:
                    raise ValueError("360 view URL and storage key must be set together.")
                # Explicitly clearing either half clears the pair so the DB can
                # never retain a stale URL or storage key.
                self.view_360_url = None
                self.view_360_key = None
            else:
                self.view_360_url, self.view_360_key = _normalize_view_360(
                    self.view_360_url, self.view_360_key
                )
        return self


class ProductListResponse(BaseModel):
    items: list[ProductOut]
    total: int
    limit: int
    offset: int


class ProductOptionOut(BaseModel):
    """Slim row for admin dropdowns (variants, offers) — no images/stock."""

    id: int
    name: str
    sku: str
    price: float = 0


class ProductOptionListResponse(BaseModel):
    items: list[ProductOptionOut]
    total: int
    limit: int
    offset: int


class NextSkuOut(BaseModel):
    sku: str


class VariantListResponse(BaseModel):
    items: list[ProductVariantOut]
    total: int
    limit: int
    offset: int
