"""Customer taxonomy feed for storefront filters."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dto.taxonomy_dto import CustomerBrandOut, CustomerCategoryOut, CustomerStoreOut
from app.schemas import Brand, Category, Store

router = APIRouter(prefix="/customer", tags=["customer-catalog"])

# Verified Unsplash eyewear photos only (checked content + HTTP 200).
_U = "https://images.unsplash.com"
EYEGLASSES = f"{_U}/photo-1574258495973-f010dfbb5371?auto=format&fit=crop&w=900&q=70"
SUNGLASSES = f"{_U}/photo-1511499767150-a48a237f0083?auto=format&fit=crop&w=900&q=70"
READING = f"{_U}/photo-1591076482161-42ce6da69f67?auto=format&fit=crop&w=900&q=70"
WAYFARER = f"{_U}/photo-1572635196237-14b3f281503f?auto=format&fit=crop&w=900&q=70"
CAT_EYE = f"{_U}/photo-1508296695146-257a814070b4?auto=format&fit=crop&w=900&q=70"
BEACH_SUN = f"{_U}/photo-1473496169904-658ba7c44d8a?auto=format&fit=crop&w=900&q=70"
LIFESTYLE_SUN = f"{_U}/photo-1577803645773-f96470509666?auto=format&fit=crop&w=900&q=70"
CASE_SUN = f"{_U}/photo-1556306535-38febf6782e7?auto=format&fit=crop&w=900&q=70"

# Stable images keyed by category slug for storefront cards.
CATEGORY_IMAGES = {
    "eyeglasses": EYEGLASSES,
    "sunglasses": SUNGLASSES,
    "prescription-sunglasses": BEACH_SUN,
    "reading-glasses": READING,
    "computer-glasses": EYEGLASSES,
    "blue-light": LIFESTYLE_SUN,
    "contact-lenses": READING,  # clear optical lenses (no virus / non-eyewear art)
    "lens-solutions": CASE_SUN,
    "accessories": CAT_EYE,
    "kids": EYEGLASSES,
    "kids-collection": EYEGLASSES,
    "sports": WAYFARER,
    "sports-eyewear": WAYFARER,
    "sunframes": SUNGLASSES,
    "designer-frames": CAT_EYE,
    "progressive-lenses": READING,
}


@router.get("/categories", response_model=list[CustomerCategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CustomerCategoryOut]:
    rows = db.scalars(
        select(Category)
        .where(Category.status == "active")
        .order_by(Category.name.asc())
    ).all()
    return [
        CustomerCategoryOut(
            id=r.id,
            name=r.name,
            slug=r.slug,
            image=CATEGORY_IMAGES.get(r.slug) or EYEGLASSES,
        )
        for r in rows
    ]


@router.get("/brands", response_model=list[CustomerBrandOut])
def list_brands(db: Session = Depends(get_db)) -> list[CustomerBrandOut]:
    rows = db.scalars(
        select(Brand).where(Brand.status == "active").order_by(Brand.name.asc())
    ).all()
    return [CustomerBrandOut(id=r.id, name=r.name, slug=r.slug) for r in rows]


@router.get("/stores", response_model=list[CustomerStoreOut])
def list_stores(db: Session = Depends(get_db)) -> list[CustomerStoreOut]:
    """Public studio list for the eye-test booking picker and checkout pickup."""
    rows = db.scalars(
        select(Store).where(Store.status == "Open").order_by(Store.city.asc())
    ).all()
    return [
        CustomerStoreOut(
            id=r.id,
            name=r.name,
            city=r.city or "",
            address=r.address or "",
            phone=r.phone or "",
        )
        for r in rows
    ]
