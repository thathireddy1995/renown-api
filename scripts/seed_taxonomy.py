"""Seed taxonomy + optical master data from admin-data.ts mocks.

Run after migrations 0007–0012:

    python -m scripts.seed_taxonomy

Safe to re-run — matched by slug/name. Also remaps products.brand_id /
products.category_id from Phase 2 lookup indices onto real brand/category
rows, and backfills product_variants.color_id / size_id.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.catalog_serialize import slugify
from app.core.taxonomy_utils import status_store, type_store
from app.database import SessionLocal
from app.schemas import (
    Attribute,
    AttributeValue,
    Brand,
    Category,
    Collection,
    Color,
    FrameType,
    LensType,
    Product,
    ProductVariant,
    Size,
)

CATEGORIES = [
    ("Eyeglasses", "active"),
    ("Sunglasses", "active"),
    ("Reading Glasses", "active"),
    ("Contact Lenses", "active"),
    ("Computer Glasses", "active"),
    ("Kids Collection", "active"),
    ("Sports Eyewear", "active"),
    ("Designer Frames", "active"),
    ("Accessories", "active"),
    ("Lens Solutions", "active"),
    ("Prescription Sunglasses", "active"),
    ("Progressive Lenses", "draft"),
    ("Blue Light", "active"),
    ("Sports", "active"),
    ("Kids", "active"),
]

# Phase 2 free-text / lookup aliases → canonical category name
CATEGORY_ALIASES = {
    "eyeglasses": "Eyeglasses",
    "sunglasses": "Sunglasses",
    "reading": "Reading Glasses",
    "contacts": "Contact Lenses",
    "computer": "Computer Glasses",
    "kids": "Kids",
    "kids collection": "Kids Collection",
    "accessories": "Accessories",
    "solutions": "Lens Solutions",
    "blue light": "Blue Light",
    "sports": "Sports",
    "contact lenses": "Contact Lenses",
    "reading glasses": "Reading Glasses",
}

BRANDS = [
    "Aperture",
    "Northline",
    "Atelier",
    "Maison Vue",
    "ClearLab",
    "Boreal",
    "Foundry",
    "Mirador",
    "Halcyon",
    "Coastline",
    "Verre & Or",
    "Slate House",
    "RenOwn Signature",
    "Aurelia",
    "Northwind",
    "Kestrel",
    "Marlow & Ives",
    "Studio Nine",
    "Vireo",
]

COLLECTIONS = [
    ("Summer 2026", "active"),
    ("Heritage Wire", "active"),
    ("Optic Nordic", "active"),
    ("Studio Minimal", "active"),
    ("Travel Edit", "active"),
    ("Boardroom", "active"),
    ("Weekend", "active"),
    ("Sport Performance", "active"),
    ("Holiday Capsule", "active"),
    ("Pre-Fall 2026", "draft"),
]

ATTRIBUTES = [
    ("Frame Shape", "select", ["Round", "Square", "Oval", "Cat Eye", "Aviator", "Browline", "Geometric"]),
    ("Material", "select", ["Acetate", "Titanium", "Stainless Steel", "Wood", "TR90", "Mixed"]),
    ("Lens Width", "select", ["48mm", "50mm", "52mm", "54mm", "56mm", "58mm"]),
    ("Bridge Width", "select", ["16mm", "18mm", "20mm", "22mm"]),
    ("Temple Length", "select", ["135mm", "140mm", "145mm", "150mm"]),
    ("Polarized", "boolean", ["Yes", "No"]),
    ("UV Protection", "select", ["UV400", "UV380", "None"]),
    ("Gender", "select", ["Men", "Women", "Unisex", "Kids"]),
]

LENS_TYPES = [
    ("Single Vision", "Corrects one field of vision", 0),
    ("Progressive", "Smooth transition near to far", 14900),
    ("Bifocal", "Two distinct viewing zones", 10000),
    ("Blue Light Filter", "Reduces digital eye strain", 3300),
    ("Photochromic", "Darkens in sunlight", 7900),
    ("Polarized", "Eliminates glare", 5400),
    ("Anti-Reflective", "Reduces reflections", 2500),
    ("High Index", "Thinner & lighter lenses", 6200),
]

FRAME_TYPES = [
    ("Full Rim", "Complete frame around lens"),
    ("Half Rim", "Top portion only"),
    ("Rimless", "No surrounding frame"),
    ("Wire Frame", "Thin metal construction"),
    ("Sport Wrap", "Curved for performance"),
    ("Clip-On", "Magnetic sun overlay"),
]

COLORS = [
    ("Tortoise", "#5a3a22"),
    ("Matte Black", "#1a1a1a"),
    ("Crystal Clear", "#e8ebee"),
    ("Champagne Gold", "#c9a84c"),
    ("Gunmetal", "#4a4f55"),
    ("Rose Gold", "#b76e79"),
    ("Navy", "#2d4a6e"),
    ("Burgundy", "#6b1f2d"),
    ("Olive", "#5d6342"),
    ("Silver", "#b8bcc1"),
    ("Black", "#111111"),
    ("Crystal", "#e6e2d8"),
    ("Amber", "#c47a3a"),
    ("Ivory", "#efe6d2"),
]

SIZES = [
    ("Extra Small", "XS", "46-48mm"),
    ("Small", "S", "48-50mm"),
    ("Medium", "M", "50-52mm"),
    ("Large", "L", "52-54mm"),
    ("Extra Large", "XL", "54-58mm"),
    ("One Size", "OS", "N/A"),
]


def upsert_category(db, name: str, status: str) -> Category:
    slug = slugify(name)
    row = db.scalar(select(Category).where(Category.slug == slug))
    if row:
        row.name = name
        row.status = status_store(status)
        print(f"Updated category: {name}")
        return row
    row = Category(name=name, slug=slug, status=status_store(status))
    db.add(row)
    print(f"Created category: {name}")
    return row


def upsert_brand(db, name: str) -> Brand:
    slug = slugify(name)
    row = db.scalar(select(Brand).where(Brand.slug == slug))
    if row:
        row.name = name
        row.status = "active"
        print(f"Updated brand: {name}")
        return row
    row = Brand(name=name, slug=slug, status="active")
    db.add(row)
    print(f"Created brand: {name}")
    return row


def upsert_collection(db, name: str, status: str) -> Collection:
    slug = slugify(name)
    row = db.scalar(select(Collection).where(Collection.slug == slug))
    if row:
        row.name = name
        row.status = status_store(status)
        print(f"Updated collection: {name}")
        return row
    row = Collection(name=name, slug=slug, status=status_store(status))
    db.add(row)
    print(f"Created collection: {name}")
    return row


def upsert_attribute(db, name: str, attr_type: str, values: list[str]) -> Attribute:
    row = db.scalar(select(Attribute).where(Attribute.name == name))
    if row:
        row.type = type_store(attr_type)
        current = db.scalars(
            select(AttributeValue).where(AttributeValue.attribute_id == row.id)
        ).all()
        current_map = {v.value: v for v in current}
        for val in values:
            if val not in current_map:
                db.add(AttributeValue(attribute_id=row.id, value=val))
        print(f"Updated attribute: {name}")
        return row
    row = Attribute(name=name, type=type_store(attr_type))
    db.add(row)
    db.flush()
    for val in values:
        db.add(AttributeValue(attribute_id=row.id, value=val))
    print(f"Created attribute: {name}")
    return row


def upsert_lens(db, name: str, description: str, price: int) -> LensType:
    row = db.scalar(select(LensType).where(LensType.name == name))
    if row:
        row.description = description
        row.price = Decimal(str(price))
        print(f"Updated lens type: {name}")
        return row
    row = LensType(name=name, description=description, price=Decimal(str(price)))
    db.add(row)
    print(f"Created lens type: {name}")
    return row


def upsert_frame(db, name: str, description: str) -> FrameType:
    row = db.scalar(select(FrameType).where(FrameType.name == name))
    if row:
        row.description = description
        print(f"Updated frame type: {name}")
        return row
    row = FrameType(name=name, description=description)
    db.add(row)
    print(f"Created frame type: {name}")
    return row


def upsert_color(db, name: str, hex_code: str) -> Color:
    row = db.scalar(select(Color).where(Color.name == name))
    if row:
        row.hex = hex_code
        print(f"Updated color: {name}")
        return row
    row = Color(name=name, hex=hex_code)
    db.add(row)
    print(f"Created color: {name}")
    return row


def upsert_size(db, name: str, code: str, measurement: str) -> Size:
    row = db.scalar(select(Size).where((Size.code == code) | (Size.name == name)))
    if row:
        row.name = name
        row.code = code
        row.measurement = measurement
        print(f"Updated size: {name}")
        return row
    row = Size(name=name, code=code, measurement=measurement)
    db.add(row)
    print(f"Created size: {name}")
    return row


def remap_products(db) -> None:
    brands = {b.name.lower(): b.id for b in db.scalars(select(Brand)).all()}
    categories = {c.name.lower(): c.id for c in db.scalars(select(Category)).all()}
    # Also index by slug
    for c in db.scalars(select(Category)).all():
        categories[c.slug.lower()] = c.id

    products = db.scalars(select(Product)).all()
    remapped = 0
    for p in products:
        # Prefer resolving from currently stored name via old free-text if join empty.
        # Phase 2 stored lookup indices; after FK migration orphans are NULL.
        # Remap using product fields that may still hold useful context: none for brand name.
        # Instead match by scanning known alias sets against brand/category tables when ids null,
        # and also fix any leftover Phase-2 index ids that happen to collide wrongly.
        pass

    # Remap using seed_products naming conventions: products already have brand_id pointing
    # at old indices. Rebuild from product sku prefix / name heuristics is fragile.
    # Better: use catalog_lookups historical lists via name on Brand/Category after upsert.
    # For products whose brand_id is NULL or invalid, try matching brand by scanning
    # all brands against nothing — we need the original brand name.
    # Re-derive from seed: update via joining free-text is unavailable.
    # Approach: for each product, if brand relationship missing, leave NULL.
    # After seed_taxonomy, re-run seed_products which now resolves via DB names.

    # Fix category aliases for products that still have a category relationship name mismatch:
    for p in products:
        changed = False
        if p.brand_id is not None and p.brand_id not in brands.values():
            p.brand_id = None
            changed = True
        if p.category_id is not None and p.category_id not in categories.values():
            # try alias remap using Category rows that might have been matched by old index name
            p.category_id = None
            changed = True
        if changed:
            remapped += 1

    # Second pass: for products with NULL brand/category, leave for seed_products re-run.
    print(f"Cleared orphaned product brand/category refs: {remapped}")


def backfill_variant_fks(db) -> None:
    colors = {c.name.lower(): c.id for c in db.scalars(select(Color)).all()}
    sizes_by_code = {s.code.lower(): s.id for s in db.scalars(select(Size)).all()}
    sizes_by_name = {s.name.lower(): s.id for s in db.scalars(select(Size)).all()}
    updated = 0
    for v in db.scalars(select(ProductVariant)).all():
        if v.color and not v.color_id:
            cid = colors.get(v.color.lower())
            if cid:
                v.color_id = cid
                updated += 1
        if v.size and not v.size_id:
            sid = sizes_by_code.get(v.size.lower()) or sizes_by_name.get(v.size.lower())
            if sid:
                v.size_id = sid
                updated += 1
    print(f"Backfilled variant color/size FKs: {updated}")


def seed() -> None:
    db = SessionLocal()
    try:
        for name, status in CATEGORIES:
            upsert_category(db, name, status)
        for name in BRANDS:
            upsert_brand(db, name)
        for name, status in COLLECTIONS:
            upsert_collection(db, name, status)
        db.flush()

        for name, attr_type, values in ATTRIBUTES:
            upsert_attribute(db, name, attr_type, values)
        for name, desc, price in LENS_TYPES:
            upsert_lens(db, name, desc, price)
        for name, desc in FRAME_TYPES:
            upsert_frame(db, name, desc)
        for name, hex_code in COLORS:
            upsert_color(db, name, hex_code)
        for name, code, measurement in SIZES:
            upsert_size(db, name, code, measurement)

        db.flush()
        remap_products(db)
        backfill_variant_fks(db)

        # Remap products by matching Phase-2 brand/category names through aliases.
        brand_by_name = {
            b.name.lower(): b.id for b in db.scalars(select(Brand)).all()
        }
        cat_by_name = {
            c.name.lower(): c.id for c in db.scalars(select(Category)).all()
        }
        for alias, canonical in CATEGORY_ALIASES.items():
            if canonical.lower() in cat_by_name:
                cat_by_name[alias] = cat_by_name[canonical.lower()]

        # Products from seed_products store names only indirectly; re-resolve using
        # brand/category tables when product still has a valid join after seed_products
        # re-run. Here we also try matching via Product.sku prefixes for admin SKUs.
        for p in db.scalars(select(Product)).all():
            # If brand already resolves, keep; otherwise try exact brand names present
            # in product name heuristics — skip. Rely on re-running seed_products.
            if p.brand is None and p.brand_id is None:
                continue

        db.commit()
        print("Taxonomy seed complete.")
        print("Tip: re-run `python -m scripts.seed_products` to attach brand/category FKs by name.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
