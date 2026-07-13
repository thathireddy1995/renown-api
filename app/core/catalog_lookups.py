"""Temporary brand/category name lookups until Phase 3 adds real tables.

brand_id / category_id on products are forward references — FKs land in
Phase 3. Until then, seed scripts and catalog routers resolve names via
these ordered lists (1-based ids).
"""

BRANDS: list[str] = [
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

CATEGORIES: list[str] = [
    "eyeglasses",
    "sunglasses",
    "reading",
    "contacts",
    "computer",
    "kids",
    "accessories",
    "solutions",
    "Eyeglasses",
    "Sunglasses",
    "Contact Lenses",
    "Reading Glasses",
    "Blue Light",
    "Sports",
    "Kids",
    "Accessories",
]


def brand_name(brand_id: int | None) -> str:
    if brand_id is None or brand_id < 1 or brand_id > len(BRANDS):
        return ""
    return BRANDS[brand_id - 1]


def category_name(category_id: int | None) -> str:
    if category_id is None or category_id < 1 or category_id > len(CATEGORIES):
        return ""
    return CATEGORIES[category_id - 1]


def brand_id_for(name: str | None) -> int | None:
    if not name:
        return None
    try:
        return BRANDS.index(name) + 1
    except ValueError:
        return None


def category_id_for(name: str | None) -> int | None:
    if not name:
        return None
    try:
        return CATEGORIES.index(name) + 1
    except ValueError:
        # Accept title-case / slug mismatches for common admin categories.
        lowered = name.lower().replace(" ", "-")
        for i, cat in enumerate(CATEGORIES):
            if cat.lower().replace(" ", "-") == lowered:
                return i + 1
        return None
