"""Seed products, variants, and images from admin + customer mock catalogs.

Run after applying migrations 0004–0006:

    python -m scripts.seed_products

Safe to re-run — matched by slug/sku and updated in place.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.catalog_lookups import brand_id_for, category_id_for
from app.core.catalog_serialize import slugify
from app.database import SessionLocal
from app.schemas import Product, ProductImage, ProductVariant

IMG = (
    lambda photo_id: f"https://images.unsplash.com/{photo_id}?auto=format&fit=crop&w=900&q=70"
)

IMG_POOL = [
    "photo-1574258495973-f010dfbb5371",
    "photo-1511499767150-a48a237f0083",
    "photo-1509695507497-903c140c43b0",
    "photo-1577803645773-f96470509666",
    "photo-1591076482161-42ce6da69f67",
    "photo-1508296695146-257a814070b4",
    "photo-1526178613552-2b45c6c302f0",
    "photo-1602699320437-c07f39c86a83",
    "photo-1473496169904-658ba7c44d8a",
    "photo-1572635196237-14b3f281503f",
    "photo-1620006317311-6f0f88b74e04",
    "photo-1556306535-0f09a537f0a3",
    "photo-1614715838608-dd527c4f4b39",
    "photo-1633621533308-8760ad239cfa",
    "photo-1608539733292-6d75e9e4bfa2",
    "photo-1512201078372-9c6b2a0d528a",
]

ADMIN_PRODUCTS = [
    {
        "name": "Halden Round",
        "sku": "ADM-HAL-001",
        "brand": "Aperture",
        "category": "eyeglasses",
        "price": 12000,
        "is_bestseller": True,
        "stock": 42,
        "colors": [("Tortoise", "#5a3a22"), ("Matte Black", "#1a1a1a"), ("Crystal Clear", "#e8ebee")],
        "sizes": ["M", "M", "L"],
        "variant_skus": ["HAL-RND-TOR-50", "HAL-RND-BLK-50", "HAL-RND-CLR-52"],
        "variant_stocks": [42, 28, 14],
    },
    {
        "name": "Marlow Aviator",
        "sku": "ADM-MAR-002",
        "brand": "Northline",
        "category": "sunglasses",
        "price": 15700,
        "compare_at_price": 19100,
        "is_trending": True,
        "stock": 36,
        "colors": [("Champagne Gold", "#c9a84c"), ("Gunmetal", "#4a4f55"), ("Rose Gold", "#b76e79")],
        "sizes": ["L", "L", "M"],
        "variant_skus": ["MAR-AVI-GLD-54", "MAR-AVI-GUN-54", "MAR-AVI-RSE-52"],
        "variant_stocks": [36, 22, 8],
    },
    {
        "name": "Quill Reader",
        "sku": "ADM-QUI-003",
        "brand": "Atelier",
        "category": "reading",
        "price": 6600,
        "is_new": True,
        "stock": 40,
        "colors": [("Matte Black", "#1a1a1a")],
        "sizes": ["M"],
        "variant_skus": ["QUI-RDR-BLK-50"],
        "variant_stocks": [40],
    },
    {
        "name": "Pure Vision Daily",
        "sku": "ADM-PVD-004",
        "brand": "ClearLab",
        "category": "contacts",
        "price": 3200,
        "is_bestseller": True,
        "stock": 120,
        "colors": [("Crystal Clear", "#e8ebee")],
        "sizes": ["One Size"],
        "variant_skus": ["PVD-DAY-CLR-00"],
        "variant_stocks": [120],
    },
    {
        "name": "Linden Square",
        "sku": "ADM-LIN-005",
        "brand": "Aperture",
        "category": "eyeglasses",
        "price": 13700,
        "is_new": True,
        "stock": 52,
        "colors": [("Matte Black", "#1a1a1a"), ("Navy", "#2d4a6e")],
        "sizes": ["M", "M"],
        "variant_skus": ["LIN-SQR-BLK-52", "LIN-SQR-NAV-52"],
        "variant_stocks": [52, 18],
    },
    {
        "name": "Stowe Cat Eye",
        "sku": "ADM-STW-006",
        "brand": "Maison Vue",
        "category": "sunglasses",
        "price": 17800,
        "stock": 24,
        "colors": [("Tortoise", "#5a3a22"), ("Burgundy", "#6b1f2d")],
        "sizes": ["M", "M"],
        "variant_skus": ["STW-CAT-TOR-50", "STW-CAT-BRG-50"],
        "variant_stocks": [24, 11],
    },
    {
        "name": "Beacon Wire",
        "sku": "ADM-BCN-007",
        "brand": "Northline",
        "category": "eyeglasses",
        "price": 11200,
        "is_trending": True,
        "stock": 33,
        "colors": [("Champagne Gold", "#c9a84c")],
        "sizes": ["S"],
        "variant_skus": ["BCN-WIR-GLD-48"],
        "variant_stocks": [33],
    },
    {
        "name": "Ridge Polarized",
        "sku": "ADM-RDG-008",
        "brand": "Northline",
        "category": "sunglasses",
        "price": 14500,
        "is_bestseller": True,
        "stock": 48,
        "colors": [("Matte Black", "#1a1a1a")],
        "sizes": ["L"],
        "variant_skus": ["RDG-POL-BLK-54"],
        "variant_stocks": [48],
    },
    {
        "name": "Verse Reader",
        "sku": "ADM-VRS-009",
        "brand": "Atelier",
        "category": "reading",
        "price": 7400,
        "stock": 28,
        "colors": [("Tortoise", "#5a3a22")],
        "sizes": ["M"],
        "variant_skus": ["VRS-RDR-TOR-50"],
        "variant_stocks": [28],
    },
    {
        "name": "Crescent Monthly",
        "sku": "ADM-CRS-010",
        "brand": "ClearLab",
        "category": "contacts",
        "price": 4600,
        "stock": 90,
        "colors": [("Crystal Clear", "#e8ebee")],
        "sizes": ["One Size"],
        "variant_skus": ["CRS-MTH-CLR-00"],
        "variant_stocks": [90],
    },
    {
        "name": "Atlas Browline",
        "sku": "ADM-ATL-011",
        "brand": "Aperture",
        "category": "eyeglasses",
        "price": 12900,
        "compare_at_price": 16200,
        "stock": 36,
        "colors": [("Gunmetal", "#4a4f55")],
        "sizes": ["L"],
        "variant_skus": ["ATL-BRW-GUN-54"],
        "variant_stocks": [36],
    },
    {
        "name": "Soren Oval",
        "sku": "ADM-SOR-012",
        "brand": "Maison Vue",
        "category": "eyeglasses",
        "price": 14500,
        "is_new": True,
        "stock": 22,
        "colors": [("Olive", "#5d6342")],
        "sizes": ["M"],
        "variant_skus": ["SOR-OVL-OLV-52"],
        "variant_stocks": [22],
    },
]

CUSTOMER_BRANDS = [
    "RenOwn Signature",
    "Aurelia",
    "Northwind",
    "Kestrel",
    "Marlow & Ives",
    "Studio Nine",
    "Halcyon",
    "Vireo",
]
CUSTOMER_SHAPES = ["Round", "Square", "Rectangle", "Cat-Eye", "Aviator", "Oval", "Geometric", "Wayfarer"]
CUSTOMER_MATERIALS = ["Acetate", "Titanium", "Metal", "TR90", "Wood", "Mixed"]
CUSTOMER_COLORS = [
    ("Tortoise", "#6b4423"),
    ("Black", "#111111"),
    ("Crystal", "#e6e2d8"),
    ("Amber", "#c47a3a"),
    ("Olive", "#5b6a43"),
    ("Rose Gold", "#c88b7a"),
    ("Navy", "#1e2a44"),
    ("Ivory", "#efe6d2"),
]
CUSTOMER_CATS = [
    "Eyeglasses",
    "Sunglasses",
    "Contact Lenses",
    "Reading Glasses",
    "Blue Light",
    "Sports",
    "Kids",
    "Accessories",
]
CUSTOMER_NAMES = [
    "Marlow", "Aurora", "Ridge", "Crescent", "Halcyon", "Vireo", "Kestrel", "Osprey",
    "Linden", "Ember", "Solace", "Palette", "Thatcher", "Wren", "Cypress", "Hollis",
    "Bellamy", "Rowan", "Ashby", "Sable", "Piper", "North", "Vale", "Wilder",
]
CUSTOMER_SUFFIXES = ["01", "02", "Pro", "Classic", "Lite", "Edge"]
GENDERS = ["Men", "Women", "Unisex", "Kids"]
RIM_TYPES = ["Full Rim", "Half Rim", "Rimless"]
SIZES = ["Small", "Medium", "Large"]


def _pseudo(seed: int):
    x = seed

    def nxt() -> float:
        nonlocal x
        x = (x * 9301 + 49297) % 233280
        return x / 233280

    return nxt


def customer_products() -> list[dict]:
    items: list[dict] = []
    for i in range(36):
        r = _pseudo(i + 7)
        price = round((60 + r() * 240) * 100) / 100
        compare = round(price * 1.35 * 100) / 100 if i % 3 == 0 else None
        color = CUSTOMER_COLORS[i % len(CUSTOMER_COLORS)]
        name = f"{CUSTOMER_NAMES[i % len(CUSTOMER_NAMES)]} {CUSTOMER_SUFFIXES[i % 6]}"
        items.append(
            {
                "name": name,
                "sku": f"RO-{1000 + i}",
                "slug": slugify(f"{name}-{1000 + i}"),
                "brand": CUSTOMER_BRANDS[i % len(CUSTOMER_BRANDS)],
                "category": CUSTOMER_CATS[i % len(CUSTOMER_CATS)],
                "price": price,
                "compare_at_price": compare,
                "gender": GENDERS[i % 4],
                "shape": CUSTOMER_SHAPES[i % len(CUSTOMER_SHAPES)],
                "material": CUSTOMER_MATERIALS[i % len(CUSTOMER_MATERIALS)],
                "rim_type": RIM_TYPES[i % 3],
                "is_new": i % 5 == 0,
                "is_bestseller": i % 4 == 0,
                "is_trending": i % 6 == 0,
                "warranty": "2-year against defects",
                "description": (
                    "Hand-finished frames built for daily wear. Lightweight construction, "
                    "refined proportions, and premium hinges — engineered to feel invisible "
                    "from morning to midnight."
                ),
                "images": [
                    IMG(IMG_POOL[i % len(IMG_POOL)]),
                    IMG(IMG_POOL[(i + 3) % len(IMG_POOL)]),
                    IMG(IMG_POOL[(i + 7) % len(IMG_POOL)]),
                ],
                "colors": [color],
                "sizes": [SIZES[i % 3]],
                "variant_skus": [f"RO-{1000 + i}-{SIZES[i % 3][:1].upper()}"],
                "variant_stocks": [0 if i % 11 == 0 else 20 + (i % 40)],
            }
        )
    return items


def upsert_product(db, data: dict, image_urls: list[str]) -> Product:
    slug = data.get("slug") or slugify(data["name"])
    existing = db.scalar(
        select(Product).where((Product.slug == slug) | (Product.sku == data["sku"]))
    )
    brand_id = brand_id_for(db, data["brand"])
    category_id = category_id_for(db, data["category"])
    fields = dict(
        name=data["name"],
        slug=slug,
        sku=data["sku"],
        description=data.get(
            "description",
            "Hand-finished acetate frames with titanium core wire and Japanese hinges.",
        ),
        price=Decimal(str(data["price"])),
        compare_at_price=(
            Decimal(str(data["compare_at_price"]))
            if data.get("compare_at_price") is not None
            else None
        ),
        brand_id=brand_id,
        category_id=category_id,
        gender=data.get("gender"),
        shape=data.get("shape"),
        material=data.get("material"),
        rim_type=data.get("rim_type"),
        warranty=data.get("warranty", "2-year against defects"),
        is_new=bool(data.get("is_new", False)),
        is_bestseller=bool(data.get("is_bestseller", False)),
        is_trending=bool(data.get("is_trending", False)),
        status="active",
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        product = existing
        product.images.clear()
        product.variants.clear()
        db.flush()
        print(f"Updated: {product.sku} ({product.name})")
    else:
        product = Product(**fields)
        db.add(product)
        db.flush()
        print(f"Created: {product.sku} ({product.name})")

    for i, url in enumerate(image_urls):
        db.add(ProductImage(product_id=product.id, url=url, sort_order=i))

    colors = data.get("colors") or [("Matte Black", "#1a1a1a")]
    sizes = data.get("sizes") or ["M"]
    skus = data.get("variant_skus") or [f"{data['sku']}-V1"]
    stocks = data.get("variant_stocks") or [data.get("stock", 20)]
    for i, sku in enumerate(skus):
        color_name, color_hex = colors[i % len(colors)]
        db.add(
            ProductVariant(
                product_id=product.id,
                sku=sku,
                color=color_name,
                color_hex=color_hex,
                size=sizes[i % len(sizes)],
                price=Decimal(str(data["price"])),
                stock=stocks[i % len(stocks)],
            )
        )
    return product


def seed() -> None:
    db = SessionLocal()
    try:
        for i, item in enumerate(ADMIN_PRODUCTS):
            urls = [IMG(IMG_POOL[i % len(IMG_POOL)]), IMG(IMG_POOL[(i + 5) % len(IMG_POOL)])]
            upsert_product(db, item, urls)

        for item in customer_products():
            upsert_product(db, item, item["images"])

        db.commit()
        print("Seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
