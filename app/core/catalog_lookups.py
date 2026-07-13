"""Resolve brand/category names via real brands/categories tables (Phase 3)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.schemas import Brand, Category


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
