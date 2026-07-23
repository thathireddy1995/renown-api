"""Serialize Product ORM rows into ProductOut / ProductVariantOut DTOs."""

from decimal import Decimal

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
        created_at=variant.created_at,
        updated_at=variant.updated_at,
    )


def product_out(product: Product, *, public_id: str | None = None) -> ProductOut:
    """Build a UI-shaped ProductOut. public_id defaults to slug so customer
    ProductCard links (/products/$id) keep working without UI rewrites."""
    images = [img.url for img in (product.images or [])]
    variants_live = live_variants(product.variants)
    variants = [variant_out(v, product.name) for v in variants_live]
    stock = sum(v.stock for v in variants_live)
    first = variants_live[0] if variants_live else None
    brand = product.brand.name if product.brand else ""
    category = product.category.name if product.category else ""
    price = _money(product.price) or 0.0
    compare = _money(product.compare_at_price)
    offer = None
    if compare and compare > price:
        pct = int(round((1 - price / compare) * 100))
        if pct > 0:
            offer = f"{pct}% OFF"

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
        description=product.description,
        price=price,
        compare_at_price=compare,
        compareAt=compare,
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
        rating=0,
        reviews=0,
        tags=[],
        offer=offer,
        originalPrice=compare,
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
