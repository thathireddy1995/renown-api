"""Admin catalog — products CRUD under /admin/catalog."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.catalog_lookups import brand_id_for, category_id_for
from app.core.catalog_serialize import product_out, slugify
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.catalog_dto import (
    ProductCreate,
    ProductListResponse,
    ProductOut,
    ProductUpdate,
)
from app.schemas import Product, ProductImage, ProductVariant

router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"], dependencies=[Depends(require_role("admin"))])


def _load_product(db: Session, product_id: int) -> Product | None:
    return db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.brand),
            selectinload(Product.category),
        )
    )


def _resolve_brand_category(
    db: Session,
    brand: str | None,
    brand_id: int | None,
    category: str | None,
    category_id: int | None,
) -> tuple[int | None, int | None]:
    resolved_brand = brand_id if brand_id is not None else brand_id_for(db, brand)
    resolved_category = (
        category_id if category_id is not None else category_id_for(db, category)
    )
    return resolved_brand, resolved_category


@router.get("/products", response_model=ProductListResponse)
def list_products(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    brand: str | None = None,
    brand_id: int | None = None,
    category: str | None = None,
    category_id: int | None = None,
    search: str | None = Query(None, alias="q"),
) -> ProductListResponse:
    limit, offset = page
    stmt = select(Product)
    count_stmt = select(func.count()).select_from(Product)

    if status_filter:
        stmt = stmt.where(Product.status == status_filter)
        count_stmt = count_stmt.where(Product.status == status_filter)

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

    if search:
        like = f"%{search.strip()}%"
        filt = or_(Product.name.ilike(like), Product.sku.ilike(like), Product.slug.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.options(
            selectinload(Product.variants),
            selectinload(Product.images),
            selectinload(Product.brand),
            selectinload(Product.category),
        )
        .order_by(Product.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    return ProductListResponse(
        items=[product_out(p, public_id=str(p.id)) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductOut:
    product = _load_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product_out(product, public_id=str(product.id))


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> ProductOut:
    slug = payload.slug or slugify(payload.name)
    existing = db.scalar(
        select(Product).where(or_(Product.slug == slug, Product.sku == payload.sku))
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A product with this slug or SKU already exists.",
        )

    brand_id, category_id = _resolve_brand_category(
        db, payload.brand, payload.brand_id, payload.category, payload.category_id
    )

    product = Product(
        name=payload.name,
        slug=slug,
        sku=payload.sku,
        description=payload.description,
        price=payload.price,
        compare_at_price=payload.compare_at_price,
        brand_id=brand_id,
        category_id=category_id,
        gender=payload.gender,
        shape=payload.shape,
        material=payload.material,
        rim_type=payload.rim_type,
        warranty=payload.warranty,
        is_new=payload.is_new,
        is_bestseller=payload.is_bestseller,
        is_trending=payload.is_trending,
        status=payload.status or "draft",
    )
    db.add(product)
    db.flush()

    for img in payload.images:
        db.add(
            ProductImage(product_id=product.id, url=img.url, sort_order=img.sort_order)
        )

    for v in payload.variants:
        db.add(
            ProductVariant(
                product_id=product.id,
                sku=v.sku,
                color=v.color,
                color_hex=v.color_hex,
                size=v.size,
                price=v.price if v.price is not None else payload.price,
                stock=v.stock,
            )
        )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    product = _load_product(db, product.id)
    assert product is not None
    return product_out(product, public_id=str(product.id))


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)
) -> ProductOut:
    product = _load_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    data = payload.model_dump(exclude_unset=True)
    images = data.pop("images", None)
    brand = data.pop("brand", None)
    category = data.pop("category", None)

    if brand is not None or category is not None or "brand_id" in data or "category_id" in data:
        brand_id, category_id = _resolve_brand_category(
            db,
            brand,
            data.get("brand_id", product.brand_id),
            category,
            data.get("category_id", product.category_id),
        )
        data["brand_id"] = brand_id
        data["category_id"] = category_id

    for key, value in data.items():
        setattr(product, key, value)

    if images is not None:
        product.images.clear()
        db.flush()
        for img in images:
            db.add(
                ProductImage(
                    product_id=product.id,
                    url=img["url"] if isinstance(img, dict) else img.url,
                    sort_order=img["sort_order"] if isinstance(img, dict) else img.sort_order,
                )
            )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    product = _load_product(db, product_id)
    assert product is not None
    return product_out(product, public_id=str(product.id))


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    db.delete(product)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
