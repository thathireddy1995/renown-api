"""Customer taxonomy feed for storefront filters."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.company_settings import company_details
from app.database import get_db
from app.dto.settings_dto import CompanyDetailsOut
from app.dto.taxonomy_dto import (
    CustomerBrandOut,
    CustomerCategoryOut,
    CustomerCollectionOut,
    CustomerLensTypeOut,
    CustomerStoreOut,
)
from app.schemas import Brand, Category, Collection, LensType, Store

router = APIRouter(prefix="/customer", tags=["customer-catalog"])


@router.get("/company-details", response_model=CompanyDetailsOut)
def get_company_details(
    response: Response,
    db: Session = Depends(get_db),
) -> CompanyDetailsOut:
    """Live seller snapshot for tax invoices. Read-only, never cached."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return company_details(db)


@router.get("/categories", response_model=list[CustomerCategoryOut])
def list_categories(db: Session = Depends(get_db)) -> list[CustomerCategoryOut]:
    rows = db.scalars(
        select(Category)
        .where(Category.status == "active")
        .order_by(Category.sort_order.asc(), Category.name.asc(), Category.id.asc())
    ).all()
    return [
        CustomerCategoryOut(
            id=r.id,
            name=r.name,
            slug=r.slug,
            image=r.image,
            sort_order=int(r.sort_order or 0),
        )
        for r in rows
    ]


@router.get("/collections", response_model=list[CustomerCollectionOut])
def list_collections(db: Session = Depends(get_db)) -> list[CustomerCollectionOut]:
    rows = db.scalars(
        select(Collection)
        .where(Collection.status == "active")
        .order_by(Collection.id.asc())
    ).all()
    return [CustomerCollectionOut(id=r.id, name=r.name, slug=r.slug) for r in rows]


@router.get("/brands", response_model=list[CustomerBrandOut])
def list_brands(db: Session = Depends(get_db)) -> list[CustomerBrandOut]:
    rows = db.scalars(
        select(Brand).where(Brand.status == "active").order_by(Brand.name.asc())
    ).all()
    return [
        CustomerBrandOut(id=r.id, name=r.name, slug=r.slug, image=r.image) for r in rows
    ]


@router.get("/lens-types", response_model=list[CustomerLensTypeOut])
def list_lens_types(db: Session = Depends(get_db)) -> list[CustomerLensTypeOut]:
    """Lens options for the product-page power / lens picker."""
    rows = db.scalars(select(LensType).order_by(LensType.id.asc())).all()
    return [
        CustomerLensTypeOut(
            id=r.id,
            name=r.name,
            description=r.description or "",
            price=float(r.price or 0),
        )
        for r in rows
    ]


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
