"""Attach verified Unsplash eyewear images to products with empty/bad galleries.

    python -m scripts.backfill_product_images
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.schemas import Product, ProductImage

IMG = lambda photo_id: f"https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w=900&q=70"

# Verified eyewear-only photo ids (content + HTTP 200 checked).
EYEGLASSES = [
    "photo-1574258495973-f010dfbb5371",
    "photo-1591076482161-42ce6da69f67",
]
SUNGLASSES = [
    "photo-1511499767150-a48a237f0083",
    "photo-1572635196237-14b3f281503f",
    "photo-1473496169904-658ba7c44d8a",
    "photo-1577803645773-f96470509666",
]
READING = [
    "photo-1591076482161-42ce6da69f67",
    "photo-1574258495973-f010dfbb5371",
]
ACCESSORIES = [
    "photo-1508296695146-257a814070b4",
    "photo-1556306535-38febf6782e7",
]
DEFAULT_POOL = EYEGLASSES + SUNGLASSES

BY_CATEGORY: dict[str, list[str]] = {
    "eyeglasses": EYEGLASSES,
    "sunglasses": SUNGLASSES,
    "prescription-sunglasses": SUNGLASSES,
    "sunframes": SUNGLASSES,
    "reading": READING,
    "reading-glasses": READING,
    "computer-glasses": EYEGLASSES,
    "blue-light": EYEGLASSES + ["photo-1577803645773-f96470509666"],
    "contacts": READING,
    "contact-lenses": READING,
    "lens-solutions": ACCESSORIES,
    "accessories": ACCESSORIES,
    "kids": EYEGLASSES,
    "kids-collection": EYEGLASSES,
    "sports": SUNGLASSES,
    "sports-eyewear": SUNGLASSES,
    "designer-frames": ACCESSORIES,
    "progressive-lenses": READING,
}

# Known bad / irrelevant URLs previously used — force replace when present.
BAD_FRAGMENTS = (
    "photo-1583324113626-70df0f4deaab",  # virus
    "photo-1512253022256-19f3d9c8b7ee",  # 404
    "photo-1526178613552-2b45c6c302f0",  # clothing sale
    "photo-1556306535-0f09a537f0a3",  # hat
    "photo-1614715838608-dd527c4f4b39",  # 404
    "photo-1602699320437-c07f39c86a83",  # 404
    "photo-1633621533308-8760ad239cfa",  # 404
    "photo-1581594693702-fbdc51b2763b",  # blood tubes
    "photo-1584308666744-24d5c474f2ae",  # pills
    "photo-1512201078372-9c6b2a0d528a",
    "photo-1620006317311-6f0f88b74e04",
    "photo-1608539733292-6d75e9e4bfa2",
)


def _category_key(product: Product) -> str:
    cat = product.category
    if not cat:
        return ""
    for attr in ("slug", "name"):
        raw = getattr(cat, attr, None) or ""
        key = str(raw).strip().lower().replace(" ", "-")
        if key in BY_CATEGORY:
            return key
        for candidate in BY_CATEGORY:
            if candidate in key or key in candidate:
                return candidate
    return ""


def _urls_for(product: Product, index: int) -> list[str]:
    pool = BY_CATEGORY.get(_category_key(product), DEFAULT_POOL)
    a = pool[index % len(pool)]
    b = pool[(index + 1) % len(pool)]
    c = pool[(index + 2) % len(pool)]
    return [IMG(a), IMG(b), IMG(c)]


def _needs_backfill(product: Product) -> bool:
    usable = [
        (img.url or "").strip()
        for img in product.images
        if (img.url or "").strip() and not (img.url or "").startswith("data:")
    ]
    if not usable:
        return True
    return any(any(bad in url for bad in BAD_FRAGMENTS) for url in usable)


def backfill() -> None:
    db = SessionLocal()
    try:
        products = db.scalars(
            select(Product)
            .options(selectinload(Product.images), selectinload(Product.category))
            .order_by(Product.id)
        ).all()

        updated = 0
        for i, product in enumerate(products):
            if not _needs_backfill(product):
                continue
            for img in list(product.images):
                db.delete(img)
            db.flush()
            for sort_order, url in enumerate(_urls_for(product, i)):
                db.add(ProductImage(product_id=product.id, url=url, sort_order=sort_order))
            updated += 1
            print(f"Backfilled: {product.sku} — {product.name}")

        db.commit()
        print(f"Done. Updated {updated} of {len(products)} products.")
    finally:
        db.close()


if __name__ == "__main__":
    backfill()
