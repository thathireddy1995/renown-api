import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM table models. Every table here must have
    a matching migration in /migrations — this file never creates schema on
    its own (no create_all() calls anywhere in the app)."""


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STORE_MANAGER = "store_manager"
    WAREHOUSE_MANAGER = "warehouse_manager"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'store_manager', 'warehouse_manager')",
            name="users_role_check",
        ),
        Index("ix_users_role_active", "role", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_created_at", "created_at"),
        Index("ix_customers_is_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OtpCode(Base):
    __tablename__ = "otp_codes"
    __table_args__ = (
        Index("ix_otp_codes_phone_expires_at", "phone", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, default="login")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HomeBanner(Base):
    __tablename__ = "home_banners"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="home_banners_sort_order_nonnegative"),
        Index("ix_home_banners_active_order", "is_active", "sort_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    eyebrow: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    brand_line: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    image_key: Mapped[str] = mapped_column(String(500), nullable=False)
    image_alt: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    cta_label: Mapped[str] = mapped_column(String(60), nullable=False, default="Shop Now")
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_brand_id", "brand_id"),
        Index("ix_products_category_id", "category_id"),
        Index("ix_products_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    sku: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    product_id: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # Three-tier pricing (new structure)
    buying_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    mrp: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id"), nullable=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shape: Mapped[str | None] = mapped_column(String(30), nullable=True)
    material: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rim_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    warranty: Mapped[str | None] = mapped_column(String(60), nullable=True)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_bestseller: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_trending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    brand: Mapped["Brand | None"] = relationship()
    category: Mapped["Category | None"] = relationship()
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.id",
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        Index("ix_product_variants_product_id", "product_id"),
        Index("ix_product_variants_color_id", "color_id"),
        Index("ix_product_variants_size_id", "size_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    size: Mapped[str | None] = mapped_column(String(80), nullable=True)
    color_id: Mapped[int | None] = mapped_column(ForeignKey("colors.id"), nullable=True)
    size_id: Mapped[int | None] = mapped_column(ForeignKey("sizes.id"), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Per-color/size photos (e.g. a green frame shows green photos). Empty
    # list means "no dedicated photos" — the storefront falls back to the
    # product's shared image gallery.
    images: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["Product"] = relationship(back_populates="variants")
    color_ref: Mapped["Color | None"] = relationship()
    size_ref: Mapped["Size | None"] = relationship()


class ProductImage(Base):
    __tablename__ = "product_images"
    __table_args__ = (Index("ix_product_images_product_id", "product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    product: Mapped["Product"] = relationship(back_populates="images")


class ProductReview(Base):
    __tablename__ = "product_reviews"
    __table_args__ = (
        Index("ix_product_reviews_product_id", "product_id"),
        Index("ix_product_reviews_customer_id", "customer_id"),
        Index("ix_product_reviews_product_status", "product_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer"] = relationship()
    images: Mapped[list["ProductReviewImage"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="ProductReviewImage.sort_order",
    )


class ProductReviewImage(Base):
    __tablename__ = "product_review_images"
    __table_args__ = (Index("ix_product_review_images_review_id", "review_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("product_reviews.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    review: Mapped["ProductReview"] = relationship(back_populates="images")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (Index("ix_categories_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Brand(Base):
    __tablename__ = "brands"
    __table_args__ = (
        Index("ix_brands_status", "status"),
        # Slug only needs to be unique per brand name — different brands may
        # legitimately share a slug (e.g. two brands both using "sunglasses").
        UniqueConstraint("name", "slug", name="ux_brands_name_slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (Index("ix_collections_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Attribute(Base):
    __tablename__ = "attributes"
    __table_args__ = (
        CheckConstraint("type IN ('select', 'boolean')", name="attributes_type_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    values: Mapped[list["AttributeValue"]] = relationship(
        back_populates="attribute",
        cascade="all, delete-orphan",
        order_by="AttributeValue.id",
    )


class AttributeValue(Base):
    __tablename__ = "attribute_values"
    __table_args__ = (Index("ix_attribute_values_attribute_id", "attribute_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    attribute_id: Mapped[int] = mapped_column(
        ForeignKey("attributes.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    attribute: Mapped["Attribute"] = relationship(back_populates="values")


class LensType(Base):
    __tablename__ = "lens_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FrameType(Base):
    __tablename__ = "frame_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Color(Base):
    __tablename__ = "colors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    hex: Mapped[str] = mapped_column(String(7), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Size(Base):
    __tablename__ = "sizes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    measurement: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        Index("ix_cart_items_customer_id", "customer_id"),
        Index("ix_cart_items_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    saved_for_later: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped["Product"] = relationship()
    variant: Mapped["ProductVariant | None"] = relationship()


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (Index("ix_wishlist_items_customer_id", "customer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["Product"] = relationship()


class CompareItem(Base):
    __tablename__ = "compare_items"
    __table_args__ = (Index("ix_compare_items_customer_id", "customer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product: Mapped["Product"] = relationship()


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (Index("ix_addresses_customer_id", "customer_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    line1: Mapped[str] = mapped_column(String(200), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    state: Mapped[str | None] = mapped_column(String(80), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_customer_id_status", "customer_id", "status"),
        Index("ix_orders_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    address_id: Mapped[int | None] = mapped_column(
        ForeignKey("addresses.id", ondelete="SET NULL"), nullable=True
    )
    delivery: Mapped[str] = mapped_column(String(20), nullable=False, default="ship")
    pickup_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="placed")
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    discount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    shipping_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False, default="cod")
    payment_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    razorpay_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    awb_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    courier_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shiprocket_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shiprocket_shipment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tracking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    verify_token: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
    )
    address: Mapped["Address | None"] = relationship()
    pickup_store: Mapped["Store | None"] = relationship(foreign_keys=[pickup_store_id])
    customer: Mapped["Customer"] = relationship()


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        Index("ix_order_items_order_id", "order_id"),
        Index("ix_order_items_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True
    )
    name_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
    variant: Mapped["ProductVariant | None"] = relationship()


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (Index("ix_warehouses_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    manager: Mapped[str | None] = mapped_column(String(120), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    staff: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    # Admin-visible staff portal password (users.password_hash is still used for login)
    login_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (Index("ix_stores_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    hours: Mapped[str | None] = mapped_column(String(80), nullable=True)
    manager: Mapped[str | None] = mapped_column(String(120), nullable=True)
    staff: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Open")
    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    login_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    today_revenue: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    today_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WarehouseInventory(Base):
    __tablename__ = "warehouse_inventory"
    __table_args__ = (
        Index("ix_warehouse_inventory_variant_id", "variant_id"),
        Index("ix_warehouse_inventory_warehouse_id", "warehouse_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    bin_location: Mapped[str | None] = mapped_column(String(40), nullable=True)
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    warehouse: Mapped["Warehouse"] = relationship()
    variant: Mapped["ProductVariant"] = relationship()


class StoreInventory(Base):
    __tablename__ = "store_inventory"
    __table_args__ = (
        Index("ix_store_inventory_variant_id", "variant_id"),
        Index("ix_store_inventory_store_id", "store_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False
    )
    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    on_floor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backroom: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["Store"] = relationship()
    variant: Mapped["ProductVariant"] = relationship()


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = (Index("ix_suppliers_status", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("ix_purchase_orders_supplier_id", "supplier_id"),
        Index("ix_purchase_orders_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    supplier: Mapped["Supplier"] = relationship()


class Grn(Base):
    __tablename__ = "grn"
    __table_args__ = (
        Index("ix_grn_purchase_order_id", "purchase_order_id"),
        Index("ix_grn_warehouse_id", "warehouse_id"),
        Index("ix_grn_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    purchase_order: Mapped["PurchaseOrder"] = relationship()
    warehouse: Mapped["Warehouse"] = relationship()
    items: Mapped[list["GrnItem"]] = relationship(
        back_populates="grn", cascade="all, delete-orphan"
    )


class GrnItem(Base):
    __tablename__ = "grn_items"
    __table_args__ = (
        Index("ix_grn_items_grn_id", "grn_id"),
        Index("ix_grn_items_variant_id", "variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grn_id: Mapped[int] = mapped_column(
        ForeignKey("grn.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    qty_ordered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    grn: Mapped["Grn"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class PickList(Base):
    __tablename__ = "pick_lists"
    __table_args__ = (
        Index("ix_pick_lists_warehouse_id", "warehouse_id"),
        Index("ix_pick_lists_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    list_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    wave_number: Mapped[str] = mapped_column(String(80), nullable=False)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    picker_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    warehouse: Mapped["Warehouse"] = relationship()
    items: Mapped[list["PickListItem"]] = relationship(
        back_populates="pick_list", cascade="all, delete-orphan"
    )


class PickListItem(Base):
    __tablename__ = "pick_list_items"
    __table_args__ = (
        Index("ix_pick_list_items_pick_list_id", "pick_list_id"),
        Index("ix_pick_list_items_variant_id", "variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pick_list_id: Mapped[int] = mapped_column(
        ForeignKey("pick_lists.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    picked_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    pick_list: Mapped["PickList"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class DispatchOrder(Base):
    __tablename__ = "dispatch_orders"
    __table_args__ = (
        Index("ix_dispatch_orders_warehouse_id", "warehouse_id"),
        Index("ix_dispatch_orders_status", "status"),
        Index("ix_dispatch_orders_destination_id", "destination_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    do_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    destination_type: Mapped[str] = mapped_column(String(20), nullable=False)
    destination_id: Mapped[int | None] = mapped_column(nullable=True)
    destination_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    awb: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    warehouse: Mapped["Warehouse"] = relationship()
    items: Mapped[list["DispatchOrderItem"]] = relationship(
        back_populates="dispatch_order", cascade="all, delete-orphan"
    )


class DispatchOrderItem(Base):
    __tablename__ = "dispatch_order_items"
    __table_args__ = (
        Index("ix_dispatch_order_items_dispatch_order_id", "dispatch_order_id"),
        Index("ix_dispatch_order_items_variant_id", "variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dispatch_order_id: Mapped[int] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    dispatch_order: Mapped["DispatchOrder"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class Pack(Base):
    __tablename__ = "packs"
    __table_args__ = (
        Index("ix_packs_dispatch_order_id", "dispatch_order_id"),
        Index("ix_packs_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pack_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    dispatch_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("dispatch_orders.id", ondelete="SET NULL"), nullable=True
    )
    packer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    boxes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    dispatch_order: Mapped["DispatchOrder | None"] = relationship()


class StockTransfer(Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (
        Index("ix_stock_transfers_status", "status"),
        Index("ix_stock_transfers_from_warehouse_id", "from_warehouse_id"),
        Index("ix_stock_transfers_to_warehouse_id", "to_warehouse_id"),
        Index("ix_stock_transfers_to_store_id", "to_store_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    from_warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    to_warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )
    to_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="requested")
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    eta: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    from_warehouse: Mapped["Warehouse"] = relationship(
        foreign_keys=[from_warehouse_id]
    )
    to_warehouse: Mapped["Warehouse | None"] = relationship(
        foreign_keys=[to_warehouse_id]
    )
    to_store: Mapped["Store | None"] = relationship(foreign_keys=[to_store_id])
    items: Mapped[list["StockTransferItem"]] = relationship(
        back_populates="stock_transfer", cascade="all, delete-orphan"
    )


class StockTransferItem(Base):
    __tablename__ = "stock_transfer_items"
    __table_args__ = (
        Index("ix_stock_transfer_items_stock_transfer_id", "stock_transfer_id"),
        Index("ix_stock_transfer_items_variant_id", "variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_transfer_id: Mapped[int] = mapped_column(
        ForeignKey("stock_transfers.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    stock_transfer: Mapped["StockTransfer"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class TransferRequest(Base):
    __tablename__ = "transfer_requests"
    __table_args__ = (
        Index("ix_transfer_requests_store_id", "store_id"),
        Index("ix_transfer_requests_status", "status"),
        Index("ix_transfer_requests_requester_warehouse_id", "requester_warehouse_id"),
        Index("ix_transfer_requests_target_warehouse_id", "target_warehouse_id"),
        Index("ix_transfer_requests_variant_id", "variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=True
    )
    requester_warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )
    target_warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=True
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    qty_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False, default="Medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    stock_transfer_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_transfers.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["Store | None"] = relationship(foreign_keys=[store_id])
    requester_warehouse: Mapped["Warehouse | None"] = relationship(
        foreign_keys=[requester_warehouse_id]
    )
    target_warehouse: Mapped["Warehouse | None"] = relationship(
        foreign_keys=[target_warehouse_id]
    )
    variant: Mapped["ProductVariant"] = relationship()
    stock_transfer: Mapped["StockTransfer | None"] = relationship()


class StockAllocation(Base):
    __tablename__ = "stock_allocations"
    __table_args__ = (
        Index("ix_stock_allocations_order_id", "order_id"),
        Index("ix_stock_allocations_status", "status"),
        Index("ix_stock_allocations_variant_id", "variant_id"),
        Index("ix_stock_allocations_warehouse_id", "warehouse_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    allocation_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    order_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    picker_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    order: Mapped["Order | None"] = relationship()
    variant: Mapped["ProductVariant"] = relationship()
    warehouse: Mapped["Warehouse"] = relationship()


class StoreOrder(Base):
    __tablename__ = "store_orders"
    __table_args__ = (
        Index("ix_store_orders_store_id", "store_id"),
        Index("ix_store_orders_status", "status"),
        Index("ix_store_orders_channel", "channel"),
        Index("ix_store_orders_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False, default="in_store")
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False, default="cash")
    associate_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Completed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    store: Mapped["Store"] = relationship()
    items: Mapped[list["StoreOrderItem"]] = relationship(
        back_populates="store_order", cascade="all, delete-orphan"
    )


class StoreOrderItem(Base):
    __tablename__ = "store_order_items"
    __table_args__ = (
        Index("ix_store_order_items_store_order_id", "store_order_id"),
        Index("ix_store_order_items_variant_id", "variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_order_id: Mapped[int] = mapped_column(
        ForeignKey("store_orders.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    price_snapshot: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )

    store_order: Mapped["StoreOrder"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = (Index("ix_doctors_store_id", "store_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    specialty: Mapped[str | None] = mapped_column(String(120), nullable=True)
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    store: Mapped["Store | None"] = relationship()


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(
            "appointment_type IN ('eye_test', 'fitting', 'lens_trial')",
            name="appointments_type_check",
        ),
        CheckConstraint(
            "status IN ('booked', 'confirmed', 'completed', 'cancelled')",
            name="appointments_status_check",
        ),
        Index("ix_appointments_store_id", "store_id"),
        Index("ix_appointments_scheduled_at", "scheduled_at"),
        Index("ix_appointments_status", "status"),
        Index("ix_appointments_customer_id", "customer_id"),
        Index("ix_appointments_doctor_id", "doctor_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True
    )
    appointment_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="eye_test"
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked")
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    customer: Mapped["Customer | None"] = relationship()
    store: Mapped["Store"] = relationship()
    doctor: Mapped["Doctor | None"] = relationship()


class Prescription(Base):
    __tablename__ = "prescriptions"
    __table_args__ = (
        Index("ix_prescriptions_customer_id", "customer_id"),
        Index("ix_prescriptions_doctor_id", "doctor_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True
    )
    right_sph: Mapped[str | None] = mapped_column(String(20), nullable=True)
    right_cyl: Mapped[str | None] = mapped_column(String(20), nullable=True)
    left_sph: Mapped[str | None] = mapped_column(String(20), nullable=True)
    left_cyl: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pd: Mapped[str | None] = mapped_column(String(20), nullable=True)
    recorded_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    customer: Mapped["Customer"] = relationship()
    doctor: Mapped["Doctor | None"] = relationship()


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="employees_status_check",
        ),
        Index("ix_employees_store_id", "store_id"),
        Index("ix_employees_warehouse_id", "warehouse_id"),
        Index("ix_employees_job_role", "job_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    job_role: Mapped[str] = mapped_column(String(40), nullable=False)
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"), nullable=True
    )
    warehouse_id: Mapped[int | None] = mapped_column(
        ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shift: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    mtd_sales: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    store: Mapped["Store | None"] = relationship()
    warehouse: Mapped["Warehouse | None"] = relationship()


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="import_jobs_status_check",
        ),
        Index("ix_import_jobs_status", "status"),
        Index("ix_import_jobs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False, default="products")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InventoryAudit(Base):
    __tablename__ = "inventory_audits"
    __table_args__ = (
        CheckConstraint(
            "status IN ('scheduled', 'in_progress', 'completed')",
            name="inventory_audits_status_check",
        ),
        Index("ix_inventory_audits_warehouse_id", "warehouse_id"),
        Index("ix_inventory_audits_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_number: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    zone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    auditor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    warehouse: Mapped["Warehouse"] = relationship()
    items: Mapped[list["InventoryAuditItem"]] = relationship(
        back_populates="audit", cascade="all, delete-orphan"
    )


class InventoryAuditItem(Base):
    __tablename__ = "inventory_audit_items"
    __table_args__ = (
        Index("ix_inventory_audit_items_inventory_audit_id", "inventory_audit_id"),
        Index("ix_inventory_audit_items_variant_id", "variant_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_audit_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_audits.id", ondelete="CASCADE"), nullable=False
    )
    variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False
    )
    expected_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counted_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    variance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    audit: Mapped["InventoryAudit"] = relationship(back_populates="items")
    variant: Mapped["ProductVariant"] = relationship()


class Offer(Base):
    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('FLAT', 'PERCENTAGE')",
            name="offers_discount_type_check",
        ),
        CheckConstraint(
            "apply_on IN ('PRODUCT', 'BRAND', 'CATEGORY', 'GENDER')",
            name="offers_apply_on_check",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'active', 'expired', 'inactive', 'deleted')",
            name="offers_status_check",
        ),
        CheckConstraint("discount_value > 0", name="offers_discount_value_positive"),
        CheckConstraint(
            "discount_type != 'PERCENTAGE' OR discount_value <= 100",
            name="offers_percentage_at_most_100",
        ),
        CheckConstraint("end_date > start_date", name="offers_dates_ordered"),
        Index("ix_offers_status", "status"),
        Index("ix_offers_apply_on", "apply_on"),
        Index("ix_offers_product_id", "product_id"),
        Index("ix_offers_brand_id", "brand_id"),
        Index("ix_offers_category_id", "category_id"),
        Index("ix_offers_gender", "gender"),
        Index("ix_offers_priority", "priority"),
        Index("ix_offers_dates", "start_date", "end_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)

    # Discount configuration
    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'FLAT' or 'PERCENTAGE'
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    maximum_discount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Apply offer on configuration
    apply_on: Mapped[str] = mapped_column(String(20), nullable=False)  # 'PRODUCT', 'BRAND', 'CATEGORY', 'GENDER'
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 'MALE', 'FEMALE', 'UNISEX'

    # Scheduling
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Priority for multi-offer scenarios
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Status: auto-determined except when manually deactivated
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    product: Mapped["Product | None"] = relationship()
    brand: Mapped["Brand | None"] = relationship()
    category: Mapped["Category | None"] = relationship()


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (
        CheckConstraint(
            "discount_type IN ('FLAT', 'PERCENTAGE')",
            name="coupons_discount_type_check",
        ),
        CheckConstraint(
            "apply_on IN ('ALL', 'BRAND', 'CATEGORY', 'GENDER')",
            name="coupons_apply_on_check",
        ),
        CheckConstraint(
            "status IN ('scheduled', 'active', 'expired', 'inactive', 'deleted')",
            name="coupons_status_check",
        ),
        CheckConstraint("discount_value > 0", name="coupons_discount_value_positive"),
        CheckConstraint(
            "discount_type != 'PERCENTAGE' OR discount_value <= 100",
            name="coupons_percentage_at_most_100",
        ),
        CheckConstraint("end_date > start_date", name="coupons_dates_ordered"),
        CheckConstraint("min_order_amount >= 0", name="coupons_min_order_nonnegative"),
        Index("ix_coupons_status", "status"),
        Index("ix_coupons_dates", "start_date", "end_date"),
        Index("ix_coupons_brand_id", "brand_id"),
        Index("ix_coupons_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)

    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    maximum_discount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    min_order_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    apply_on: Mapped[str] = mapped_column(String(20), nullable=False, default="ALL")
    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    per_customer_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    brand: Mapped["Brand | None"] = relationship()
    category: Mapped["Category | None"] = relationship()
    redemptions: Mapped[list["CouponRedemption"]] = relationship(
        back_populates="coupon", cascade="all, delete-orphan"
    )


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (
        Index("ix_coupon_redemptions_coupon_customer", "coupon_id", "customer_id"),
        Index("ix_coupon_redemptions_customer_id", "customer_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    coupon_id: Mapped[int] = mapped_column(
        ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    coupon: Mapped["Coupon"] = relationship(back_populates="redemptions")
