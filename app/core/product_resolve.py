"""Resolve product refs (slug or numeric id) for customer cart/wishlist/compare."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas import Product


def resolve_product(db: Session, ref: str) -> Product:
    ref = (ref or "").strip()
    if not ref:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="product_id is required.",
        )
    product = None
    if ref.isdigit():
        product = db.get(Product, int(ref))
    if product is None:
        product = db.scalar(select(Product).where(Product.slug == ref))
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )
    return product


def public_product_id(product: Product) -> str:
    """Storefront product id is the slug (Phase 2 customer ProductOut.id)."""
    return product.slug
