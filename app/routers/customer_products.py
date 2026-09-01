"""Customer storefront product feed under /customer/products."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, load_only, selectinload

from app.core.catalog_lookups import brand_id_for, category_id_for, collection_id_for
from app.core.catalog_serialize import product_cards_out, product_out
from app.core.offer_pricing import _gender_key, offer_prices_for
from app.core.review_aggregates import review_aggregates_for
from app.database import get_db
from app.deps import pagination
from app.dto.catalog_dto import ProductListResponse, ProductOut
from app.schemas import Brand, Category, Collection, Product, ProductVariant

router = APIRouter(prefix="/customer/products", tags=["customer-products"])

_PRODUCT_LOAD = (
    selectinload(Product.variants),
    selectinload(Product.images),
    selectinload(Product.brand),
    selectinload(Product.category),
    selectinload(Product.collection),
)

_CARD_LOAD = (
    selectinload(Product.variants).load_only(
        ProductVariant.id,
        ProductVariant.product_id,
        ProductVariant.sku,
        ProductVariant.color,
        ProductVariant.color_hex,
        ProductVariant.size,
        ProductVariant.price,
        ProductVariant.stock,
    ),
    selectinload(Product.images),
    selectinload(Product.brand),
    selectinload(Product.category),
    selectinload(Product.collection),
)


def _active_base():
    return Product.status == "active"


@router.get(
    "/",
    response_model=ProductListResponse,
    response_model_exclude={
        "items": {
            "__all__": {
                "buying_price",
                "buyingPrice",
                "view_360_key",
                "view360Key",
            }
        },
    },
)
def list_products(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    brand: str | None = None,
    brand_id: int | None = None,
    collection: str | None = None,
    collection_id: int | None = None,
    category: str | None = None,
    category_id: int | None = None,
    gender: str | None = None,
    min_price: Decimal | None = Query(None),
    max_price: Decimal | None = Query(None),
    search: str | None = Query(None, alias="q"),
    lite: bool = Query(False),
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

    if collection_id is not None:
        resolved_collection = collection_id
    elif collection and collection.strip():
        resolved_collection = collection_id_for(db, collection)
        if resolved_collection is None:
            return ProductListResponse(items=[], total=0, limit=limit, offset=offset)
    else:
        resolved_collection = None
    if resolved_collection is not None:
        stmt = stmt.where(Product.collection_id == resolved_collection)
        count_stmt = count_stmt.where(Product.collection_id == resolved_collection)

    requested_gender = _gender_key(gender)
    if requested_gender:
        if requested_gender == "KIDS":
            gender_match = func.upper(func.trim(func.coalesce(Product.gender, ""))) == "KIDS"
        elif requested_gender in {"MALE", "FEMALE"}:
            gender_match = func.upper(func.trim(func.coalesce(Product.gender, ""))).in_(
                (requested_gender, "UNISEX", "MEN" if requested_gender == "MALE" else "WOMEN")
            )
        else:
            gender_match = func.upper(func.trim(func.coalesce(Product.gender, ""))) == requested_gender
        stmt = stmt.where(gender_match)
        count_stmt = count_stmt.where(gender_match)

    if min_price is not None:
        stmt = stmt.where(Product.selling_price >= min_price)
        count_stmt = count_stmt.where(Product.selling_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.selling_price <= max_price)
        count_stmt = count_stmt.where(Product.selling_price <= max_price)

    if search:
        like = f"%{search.strip()}%"
        # Match on the product's own fields as well as its brand/category
        # names, so searching "sunglasses" or "Aperture" finds matching
        # products even when those words aren't in the name/SKU/description.
        filt = or_(
            Product.name.ilike(like),
            Product.sku.ilike(like),
            Product.slug.ilike(like),
            Product.product_id.ilike(like),
            Product.description.ilike(like),
            Product.brand.has(Brand.name.ilike(like)),
            Product.category.has(Category.name.ilike(like)),
            Product.collection.has(Collection.name.ilike(like)),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.options(*(_CARD_LOAD if lite else _PRODUCT_LOAD))
        .order_by(Product.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    if lite:
        items = product_cards_out(db, list(rows))
    else:
        aggregates = review_aggregates_for(db, [p.id for p in rows])
        offer_prices = offer_prices_for(db, list(rows))
        items = [
            product_out(
                p,
                rating=aggregates.get(p.id, (0.0, 0))[0],
                reviews=aggregates.get(p.id, (0.0, 0))[1],
                offer_price=offer_prices.get(p.id),
            )
            for p in rows
        ]

    return ProductListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{slug}",
    response_model=ProductOut,
    response_model_exclude={
        "buying_price",
        "buyingPrice",
        "view_360_key",
        "view360Key",
    },
)
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
    avg, count = review_aggregates_for(db, [product.id]).get(product.id, (0.0, 0))
    offer_price = offer_prices_for(db, [product]).get(product.id)
    return product_out(product, rating=avg, reviews=count, offer_price=offer_price)
