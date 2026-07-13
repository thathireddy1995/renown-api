"""Customer taxonomy feed for storefront filters."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dto.taxonomy_dto import CustomerBrandOut, CustomerCategoryOut
from app.schemas import Brand, Category

router = APIRouter(prefix="/customer", tags=["customer-catalog"])

# Stable Unsplash images keyed by category slug for storefront cards.
CATEGORY_IMAGES = {
    "eyeglasses": "https://images.unsplash.com/photo-1574258495973-f010dfbb5371?auto=format&fit=crop&w=900&q=70",
    "sunglasses": "https://images.unsplash.com/photo-1511499767150-a48a237f0083?auto=format&fit=crop&w=900&q=70",
    "contact-lenses": "https://images.unsplash.com/photo-1583324113626-70df0f4deaab?auto=format&fit=crop&w=900&q=70",
    "reading-glasses": "https://images.unsplash.com/photo-1591076482161-42ce6da69f67?auto=format&fit=crop&w=900&q=70",
    "blue-light": "https://images.unsplash.com/photo-1577803645773-f96470509666?auto=format&fit=crop&w=900&q=70",
    "sports": "https://images.unsplash.com/photo-1526178613552-2b45c6c302f0?auto=format&fit=crop&w=900&q=70",
    "kids": "https://images.unsplash.com/photo-1512253022256-19f3d9c8b7ee?auto=format&fit=crop&w=900&q=70",
    "accessories": "https://images.unsplash.com/photo-1508296695146-257a814070b4?auto=format&fit=crop&w=900&q=70",
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
            image=CATEGORY_IMAGES.get(r.slug),
        )
        for r in rows
    ]


@router.get("/brands", response_model=list[CustomerBrandOut])
def list_brands(db: Session = Depends(get_db)) -> list[CustomerBrandOut]:
    rows = db.scalars(
        select(Brand).where(Brand.status == "active").order_by(Brand.name.asc())
    ).all()
    return [CustomerBrandOut(id=r.id, name=r.name, slug=r.slug) for r in rows]
