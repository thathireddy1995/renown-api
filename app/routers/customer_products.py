"""Customer storefront product feed under /customer/products."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.catalog_lookups import brand_id_for, category_id_for
from app.core.catalog_serialize import product_out
from app.database import get_db
from app.deps import pagination
from app.dto.catalog_dto import ProductListResponse, ProductOut
from app.schemas import Brand, Category, Product

router = APIRouter(prefix="/customer/products", tags=["customer-products"])

_PRODUCT_LOAD = (
    selectinload(Product.variants),
    selectinload(Product.images),
    selectinload(Product.brand),
    selectinload(Product.category),
)


def _active_base():
    return Product.status == "active"


@router.get("/", response_model=ProductListResponse)
def list_products(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    brand: str | None = None,
    brand_id: int | None = None,
    category: str | None = None,
    category_id: int | None = None,
    min_price: Decimal | None = Query(None),
    max_price: Decimal | None = Query(None),
    search: str | None = Query(None, alias="q"),
) -> ProductListResponse:
    limit, offset = page
    stmt = select(Product).where(_active_base())
    count_stmt = select(func.count()).select_from(Product).where(_active_base())

    resolved_brand = brand_id if brand_id is not None else brand_id_for(db, brand)
    if resolved_brand is not None:
        stmt = stmt.where(Product.brand_id == resolved_brand)
        count_stmt = count_stmt.where(Product.brand_id == resolved_brand)

    resolved_category = (
        category_id if category_id is not None else category_id_for(db, category)
    )
    if resolved_category is not None:
        stmt = stmt.where(Product.category_id == resolved_category)
        count_stmt = count_stmt.where(Product.category_id == resolved_category)

    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
        count_stmt = count_stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
        count_stmt = count_stmt.where(Product.price <= max_price)

    if search:
        like = f"%{search.strip()}%"
        # Match on the product's own fields as well as its brand/category
        # names, so searching "sunglasses" or "Aperture" finds matching
        # products even when those words aren't in the name/SKU/description.
        filt = or_(
            Product.name.ilike(like),
            Product.sku.ilike(like),
            Product.slug.ilike(like),
            Product.description.ilike(like),
            Product.brand.has(Brand.name.ilike(like)),
            Product.category.has(Category.name.ilike(like)),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.options(*_PRODUCT_LOAD)
        .order_by(Product.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    return ProductListResponse(
        items=[product_out(p) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{slug}", response_model=ProductOut)
def get_product(slug: str, db: Session = Depends(get_db)) -> ProductOut:
    product = db.scalar(
        select(Product)
        .where(Product.slug == slug, _active_base())
        .options(*_PRODUCT_LOAD)
    )
    if not product and slug.isdigit():
        product = db.scalar(
            select(Product)
            .where(Product.id == int(slug), _active_base())
            .options(*_PRODUCT_LOAD)
        )
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product_out(product)
