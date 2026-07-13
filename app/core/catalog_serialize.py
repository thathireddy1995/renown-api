"""Serialize Product ORM rows into ProductOut / ProductVariantOut DTOs."""

from decimal import Decimal

from app.dto.catalog_dto import ProductOut, ProductVariantOut
from app.schemas import Product, ProductVariant


def _money(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def variant_out(variant: ProductVariant, product_name: str = "") -> ProductVariantOut:
    return ProductVariantOut(
        id=variant.id,
        product_id=variant.product_id,
        product=product_name or (variant.product.name if variant.product else ""),
        sku=variant.sku,
        color=variant.color,
        color_hex=variant.color_hex,
        size=variant.size,
        price=variant.price,
        stock=variant.stock,
        created_at=variant.created_at,
        updated_at=variant.updated_at,
    )


def product_out(product: Product, *, public_id: str | None = None) -> ProductOut:
    """Build a UI-shaped ProductOut. public_id defaults to slug so customer
    ProductCard links (/products/$id) keep working without UI rewrites."""
    images = [img.url for img in (product.images or [])]
    variants = [variant_out(v, product.name) for v in (product.variants or [])]
    stock = sum(v.stock for v in (product.variants or []))
    first = (product.variants or [None])[0]
    brand = product.brand.name if product.brand else ""
    category = product.category.name if product.category else ""
    price = _money(product.price) or 0.0
    compare = _money(product.compare_at_price)
    offer = None
    if compare and compare > price:
        pct = int(round((1 - price / compare) * 100))
        if pct > 0:
            offer = f"{pct}% OFF"

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
        warranty=product.warranty or "2-year against defects",
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
        color=(first.color if first else "") or "",
        colorHex=(first.color_hex if first else "") or "",
        size=(first.size if first else "") or "",
        lensType="",
        weight="",
        rating=4.5,
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
