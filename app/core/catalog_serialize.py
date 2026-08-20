"""Serialize Product ORM rows into ProductOut / ProductVariantOut DTOs."""

from decimal import Decimal

from app.core.offer_pricing import OfferPrice
from app.dto.catalog_dto import ProductOut, ProductVariantOut
from app.schemas import Product, ProductVariant


def _money(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() in ("__deleted__", "deleted"):
        return None
    return text


def live_variants(variants: list[ProductVariant] | None) -> list[ProductVariant]:
    return [
        v
        for v in (variants or [])
        if (v.color or "") != "__deleted__" and (v.size or "") != "__deleted__"
    ]


def variant_out(variant: ProductVariant, product_name: str = "") -> ProductVariantOut:
    return ProductVariantOut(
        id=variant.id,
        product_id=variant.product_id,
        product=product_name or (variant.product.name if variant.product else ""),
        sku=variant.sku,
        color=_clean_label(variant.color),
        color_hex=variant.color_hex if _clean_label(variant.color) else None,
        size=_clean_label(variant.size),
        price=variant.price,
        stock=variant.stock,
        images=list(variant.images or []),
        created_at=variant.created_at,
        updated_at=variant.updated_at,
    )


def product_out(
    product: Product,
    *,
    public_id: str | None = None,
    rating: float = 0,
    reviews: int = 0,
    offer_price: OfferPrice | None = None,
    include_cost: bool = False,
    include_variants: bool = True,
    include_description: bool = True,
    list_image: str | None = None,
    list_stock: int | None = None,
) -> ProductOut:
    """Build a UI-shaped ProductOut. public_id defaults to slug so customer
    ProductCard links (/products/$id) keep working without UI rewrites."""
    if list_image is not None:
        images = [list_image] if list_image else []
    else:
        images = [img.url for img in (product.images or [])]
    if include_variants:
        variants_live = live_variants(product.variants)
        variants = [variant_out(v, product.name) for v in variants_live]
        stock = sum(v.stock for v in variants_live)
        first = variants_live[0] if variants_live else None
    else:
        variants = []
        stock = int(list_stock or 0)
        first = None
    brand = product.brand.name if product.brand else ""
    category = product.category.name if product.category else ""

    # Three-tier pricing: buying_price, mrp, selling_price
    buying_price = _money(product.buying_price)
    mrp = _money(product.mrp or product.compare_at_price) or _money(product.price) or 0.0
    selling_price = _money(product.selling_price or product.price) or 0.0
    price = float(offer_price.final_price) if offer_price else selling_price

    # Discount is computed from MRP vs Selling Price (before offers)
    discount_pct = 0
    offer = None
    if mrp and price > 0 and price < mrp:
        discount_pct = int(round((1 - price / mrp) * 100))
        if discount_pct > 0:
            offer = f"{discount_pct}% OFF"
    if offer_price is not None:
        offer = f"{offer_price.offer_name}: {offer_price.label}"

    color = ""
    color_hex = ""
    size = ""
    if first is not None:
        color = _clean_label(first.color) or ""
        color_hex = first.color_hex or ""
        size = _clean_label(first.size) or ""

    pid = public_id or product.slug
    return ProductOut(
        id=pid,
        db_id=product.id,
        name=product.name,
        slug=product.slug,
        sku=product.sku,
        product_id=product.product_id,
        productId=product.product_id,
        description=product.description if include_description else None,
        price=price,
        compare_at_price=mrp,
        compareAt=mrp,
        buying_price=buying_price if include_cost else None,
        buyingPrice=buying_price if include_cost else None,
        mrp=mrp,
        sellingPrice=selling_price,
        selling_price=selling_price,
        base_selling_price=selling_price,
        baseSellingPrice=selling_price,
        offer_price=float(offer_price.final_price) if offer_price else None,
        offerPrice=float(offer_price.final_price) if offer_price else None,
        offer_discount=float(offer_price.discount) if offer_price else 0,
        offerDiscount=float(offer_price.discount) if offer_price else 0,
        applied_offer_id=offer_price.offer_id if offer_price else None,
        appliedOfferId=offer_price.offer_id if offer_price else None,
        applied_offer_name=offer_price.offer_name if offer_price else None,
        appliedOfferName=offer_price.offer_name if offer_price else None,
        discount_percentage=discount_pct,
        discountPercentage=discount_pct,
        brand=brand,
        brand_id=product.brand_id,
        category=category,
        category_id=product.category_id,
        gender=product.gender,
        shape=product.shape,
        material=product.material,
        rim_type=product.rim_type,
        rimType=product.rim_type,
        warranty=product.warranty or "",
        is_new=product.is_new,
        isNew=product.is_new,
        is_bestseller=product.is_bestseller,
        isBestSeller=product.is_bestseller,
        isBestseller=product.is_bestseller,
        is_trending=product.is_trending,
        isTrending=product.is_trending,
        status=product.status,
        image=images[0] if images else "",
        images=images,
        variants=variants,
        stock=stock,
        inStock=stock > 0,
        color=color,
        colorHex=color_hex,
        size=size,
        lensType="",
        weight="",
        rating=float(rating or 0),
        reviews=int(reviews or 0),
        tags=[],
        offer=offer,
        originalPrice=mrp,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def slugify(value: str) -> str:
    out = []
    prev_dash = False
    for ch in value.lower().strip():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-") or "product"
