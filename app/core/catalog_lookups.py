"""Resolve brand/category/collection names via taxonomy tables."""

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.orm import Session

from app.schemas import Brand, Category, Collection, Product


def brand_name(brand) -> str:
    """Accept a Brand ORM row, a Product with .brand loaded, or None."""
    if brand is None:
        return ""
    if hasattr(brand, "name") and not hasattr(brand, "brand_id"):
        return brand.name or ""
    rel = getattr(brand, "brand", None)
    return rel.name if rel else ""


def category_name(category) -> str:
    if category is None:
        return ""
    if hasattr(category, "name") and not hasattr(category, "category_id"):
        return category.name or ""
    rel = getattr(category, "category", None)
    return rel.name if rel else ""


def brand_id_for(db: Session, name: str | None) -> int | None:
    if not name:
        return None
    row = db.scalar(select(Brand).where(func.lower(Brand.name) == name.strip().lower()))
    return row.id if row else None


def category_id_for(db: Session, name: str | None) -> int | None:
    if not name:
        return None
    needle = name.strip().lower()
    row = db.scalar(
        select(Category).where(
            or_(
                func.lower(Category.name) == needle,
                func.lower(Category.slug) == needle.replace(" ", "-"),
            )
        )
    )
    return row.id if row else None


def collection_ids_for(db: Session, names: list[str] | set[str]) -> dict[str, int]:
    """Map trimmed names/slugs → collection id in one query (no N+1)."""
    cleaned = [n.strip() for n in names if n and str(n).strip()]
    if not cleaned:
        return {}
    needles = {n.lower() for n in cleaned}
    slugs = {n.replace(" ", "-") for n in needles}
    rows = db.scalars(
        select(Collection).where(
            or_(
                func.lower(Collection.name).in_(needles),
                func.lower(Collection.slug).in_(slugs),
            )
        )
    ).all()
    by_key: dict[str, int] = {}
    for row in rows:
        by_key[row.name.lower()] = row.id
        by_key[row.slug.lower()] = row.id
    out: dict[str, int] = {}
    for name in cleaned:
        key = name.lower()
        cid = by_key.get(key) or by_key.get(key.replace(" ", "-"))
        if cid is not None:
            out[name] = cid
    return out


def collection_id_for(db: Session, name: str | None) -> int | None:
    if not name or not name.strip():
        return None
    return collection_ids_for(db, [name]).get(name.strip())


SKU_START = 1001


def next_product_sku(db: Session) -> str:
    """Next unused base SKU in the SKU1001, SKU1002, … sequence."""
    max_n = db.scalar(
        select(func.max(cast(func.substring(Product.sku, 4), Integer))).where(
            Product.sku.op("~")(r"^SKU[0-9]+$")
        )
    )
    n = (max_n or (SKU_START - 1)) + 1
    if n < SKU_START:
        n = SKU_START
    while db.scalar(select(Product.id).where(Product.sku == f"SKU{n}")):
        n += 1
    return f"SKU{n}"
