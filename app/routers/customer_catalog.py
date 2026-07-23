"""Customer taxonomy feed for storefront filters."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dto.taxonomy_dto import CustomerBrandOut, CustomerCategoryOut, CustomerStoreOut
from app.schemas import Brand, Category, Store

router = APIRouter(prefix="/customer", tags=["customer-catalog"])


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
            image=None,
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
