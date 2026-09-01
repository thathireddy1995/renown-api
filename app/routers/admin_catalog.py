"""Admin catalog — products CRUD under /admin/catalog."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.catalog_lookups import brand_id_for, category_id_for, collection_id_for, next_product_sku
from app.core.catalog_serialize import product_out, slugify
from app.database import get_db
from app.deps import pagination, require_role
from app.core.config import S3_PUBLIC_BUCKET
from app.core.s3_images import delete_view_360_object, presign_puts, presign_view_360_puts
from app.dto.catalog_dto import (
    ImagePresignItem,
    ImagePresignRequest,
    ImagePresignResponse,
    ProductCreate,
    ProductListResponse,
    ProductOptionListResponse,
    ProductOptionOut,
    NextSkuOut,
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
            selectinload(Product.collection),
        )
    )


def _unique_product_slug(db: Session, base_slug: str, exclude_id: int | None = None) -> str:
    """Products may legitimately share a name (different SKU/variant line),
    so don't reject on slug collision — just append -2, -3, ... until unique.
    """
    slug = base_slug[:220]
    suffix_n = 2
    while True:
        stmt = select(Product.id).where(Product.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(Product.id != exclude_id)
        if not db.scalar(stmt):
            return slug
        suffix = f"-{suffix_n}"
        slug = f"{base_slug[: 220 - len(suffix)]}{suffix}"
        suffix_n += 1


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
    collection: str | None = None,
    collection_id: int | None = None,
    category: str | None = None,
    category_id: int | None = None,
    search: str | None = Query(None, alias="q"),
) -> ProductListResponse:
    limit, offset = page
    first_image = (
        select(
            ProductImage.product_id,
            ProductImage.url,
            func.row_number()
            .over(
                partition_by=ProductImage.product_id,
                order_by=(ProductImage.sort_order.asc(), ProductImage.id.asc()),
            )
            .label("rn"),
        )
    ).subquery()
    stock_by_product = (
        select(
            ProductVariant.product_id,
            func.coalesce(func.sum(ProductVariant.stock), 0).label("list_stock"),
        )
        .where(
            ProductVariant.color != "__deleted__",
            ProductVariant.size != "__deleted__",
        )
        .group_by(ProductVariant.product_id)
    ).subquery()
    stmt = (
        select(
            Product,
            first_image.c.url.label("list_image"),
            func.coalesce(stock_by_product.c.list_stock, 0).label("list_stock"),
            func.count().over().label("total_count"),
        )
        .outerjoin(
            first_image,
            and_(first_image.c.product_id == Product.id, first_image.c.rn == 1),
        )
        .outerjoin(stock_by_product, stock_by_product.c.product_id == Product.id)
        .options(
            joinedload(Product.brand),
            joinedload(Product.category),
            joinedload(Product.collection),
        )
    )

    if status_filter:
        stmt = stmt.where(Product.status == status_filter)
    else:
        # Soft-deleted products stay in DB for order history but leave the catalog UI.
        stmt = stmt.where(Product.status != "deleted")

    resolved_brand = brand_id if brand_id is not None else brand_id_for(db, brand)
    if resolved_brand is not None:
        stmt = stmt.where(Product.brand_id == resolved_brand)

    resolved_category = (
        category_id if category_id is not None else category_id_for(db, category)
    )
    if resolved_category is not None:
        stmt = stmt.where(Product.category_id == resolved_category)

    resolved_collection = (
        collection_id if collection_id is not None else collection_id_for(db, collection)
    )
    if resolved_collection is not None:
        stmt = stmt.where(Product.collection_id == resolved_collection)

    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Product.name.ilike(like),
                Product.sku.ilike(like),
                Product.slug.ilike(like),
                Product.product_id.ilike(like),
                Product.description.ilike(like),
            )
        )

    rows = db.execute(
        stmt.order_by(Product.id.desc()).limit(limit).offset(offset)
    ).unique().all()
    total = int(rows[0].total_count) if rows else 0
    if not rows and offset > 0:
        count_stmt = select(func.count()).select_from(Product).where(Product.status != "deleted")
        if status_filter:
            count_stmt = select(func.count()).select_from(Product).where(Product.status == status_filter)
        total = db.scalar(count_stmt) or 0

    return ProductListResponse(
        items=[
            product_out(
                row[0],
                public_id=str(row[0].id),
                include_cost=True,
                include_variants=False,
                include_description=True,
                list_image=row.list_image or "",
                list_stock=int(row.list_stock or 0),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/options", response_model=ProductOptionListResponse)
def list_product_options(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> ProductOptionListResponse:
    """id/name/sku/price only — used by variant and offer dropdowns."""
    limit, offset = page
    rows = db.execute(
        select(Product, func.count().over().label("total_count"))
        .where(Product.status != "deleted")
        .order_by(Product.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    total = int(rows[0].total_count) if rows else 0
    return ProductOptionListResponse(
        items=[
            ProductOptionOut(
                id=row[0].id,
                name=row[0].name,
                sku=row[0].sku,
                price=float(row[0].selling_price or row[0].price or 0),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/next-sku", response_model=NextSkuOut)
def get_next_product_sku(db: Session = Depends(get_db)) -> NextSkuOut:
    return NextSkuOut(sku=next_product_sku(db))


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)) -> ProductOut:
    product = _load_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return product_out(product, public_id=str(product.id), include_cost=True)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)) -> ProductOut:
    sku = (payload.sku or "").strip() or next_product_sku(db)
    existing = db.scalar(select(Product).where(Product.sku == sku))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SKU already exists. Use a different base SKU.",
        )
    if payload.product_id:
        existing_pid = db.scalar(select(Product.id).where(Product.product_id == payload.product_id))
        if existing_pid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product ID already exists. Use a different Product ID.",
            )
    slug = _unique_product_slug(db, payload.slug or slugify(payload.name))

    brand_id, category_id = _resolve_brand_category(
        db, payload.brand, payload.brand_id, payload.category, payload.category_id
    )
    resolved_collection_id = (
        payload.collection_id
        if payload.collection_id is not None
        else collection_id_for(db, payload.collection)
    )

    product = Product(
        name=payload.name,
        slug=slug,
        sku=sku,
        product_id=payload.product_id,
        description=payload.description,
        price=payload.price,
        compare_at_price=payload.compare_at_price,
        buying_price=payload.buying_price,
        mrp=payload.mrp,
        selling_price=payload.selling_price,
        brand_id=brand_id,
        collection_id=resolved_collection_id,
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
        view_360_url=payload.view_360_url,
        view_360_key=payload.view_360_key,
    )
    db.add(product)
    db.flush()

    for img in payload.images:
        db.add(
            ProductImage(product_id=product.id, url=img.url, sort_order=img.sort_order)
        )

    seen_skus: set[str] = set()
    for v in payload.variants:
        sku_key = (v.sku or "").strip().lower()
        if not sku_key:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each variant needs a SKU.",
            )
        if sku_key in seen_skus:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Duplicate variant SKU in request: {v.sku}",
            )
        seen_skus.add(sku_key)
        db.add(
            ProductVariant(
                product_id=product.id,
                sku=v.sku,
                color=v.color,
                color_hex=v.color_hex,
                size=v.size,
                price=v.price if v.price is not None else payload.selling_price,
                stock=v.stock,
                images=v.images,
            )
        )

    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        msg = str(getattr(err, "orig", err)).lower()
        if "product_id" in msg or "ux_products_product_id" in msg:
            detail = "Product ID already exists. Use a different Product ID."
        else:
            detail = "SKU already exists. Use a different base SKU."
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from err
    except DataError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"A value is too long for the database (e.g. frame type / size). {err.orig}",
        ) from err
    except Exception:
        db.rollback()
        raise

    product = _load_product(db, product.id)
    assert product is not None
    return product_out(product, public_id=str(product.id), include_cost=True)


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
    collection = data.pop("collection", None)
    category = data.pop("category", None)
    old_view_360_key = product.view_360_key

    next_product_id = data.get("product_id", product.product_id)
    if next_product_id:
        taken = db.scalar(
            select(Product.id).where(
                Product.product_id == next_product_id,
                Product.id != product.id,
            )
        )
        if taken:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product ID already exists. Use a different Product ID.",
            )

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

    if "collection_id" in data:
        pass
    elif collection is not None:
        data["collection_id"] = collection_id_for(db, collection)

    next_selling_price = data.get("selling_price", product.selling_price or product.price)
    next_mrp = data.get("mrp", product.mrp or product.compare_at_price)
    if next_mrp is not None and next_selling_price > next_mrp:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selling price cannot exceed MRP.",
        )

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
    except IntegrityError as err:
        db.rollback()
        msg = str(getattr(err, "orig", err)).lower()
        if "product_id" in msg or "ux_products_product_id" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product ID already exists. Use a different Product ID.",
            ) from err
        if "sku" in msg or "ux_products_sku" in msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="SKU already exists. Use a different base SKU.",
            ) from err
        raise
    except Exception:
        db.rollback()
        raise

    product = _load_product(db, product_id)
    assert product is not None
    if old_view_360_key and old_view_360_key != product.view_360_key:
        delete_view_360_object(old_view_360_key)
    return product_out(product, public_id=str(product.id), include_cost=True)


@router.post(
    "/products/view-360/presign",
    response_model=ImagePresignResponse,
)
def presign_pending_view_360(
    payload: ImagePresignRequest,
) -> ImagePresignResponse:
    uploads = presign_view_360_puts(
        "pending",
        [(item.filename, item.content_type) for item in payload.files],
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@router.post(
    "/products/{product_id}/view-360/presign",
    response_model=ImagePresignResponse,
)
def presign_product_view_360(
    product_id: int,
    payload: ImagePresignRequest,
    db: Session = Depends(get_db),
) -> ImagePresignResponse:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    uploads = presign_view_360_puts(
        product_id,
        [(item.filename, item.content_type) for item in payload.files],
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@router.post(
    "/products/images/presign",
    response_model=ImagePresignResponse,
)
def presign_pending_product_images(
    payload: ImagePresignRequest,
) -> ImagePresignResponse:
    """Presign images before a new product exists; its DB row stores the returned URLs."""
    uploads = presign_puts(
        "pending",
        [(item.filename, item.content_type) for item in payload.files],
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@router.post(
    "/products/{product_id}/images/presign",
    response_model=ImagePresignResponse,
)
def presign_product_images(
    product_id: int,
    payload: ImagePresignRequest,
    db: Session = Depends(get_db),
) -> ImagePresignResponse:
    """Return short-lived S3 PUT URLs. Browser uploads bytes; DB only stores https URLs."""
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    uploads = presign_puts(
        product_id,
        [(item.filename, item.content_type) for item in payload.files],
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)) -> None:
    """Hard-delete when safe; otherwise soft-delete (status=deleted).

    Products referenced by order_items / inventory cannot be removed without
    breaking history — those become status=deleted and leave catalog lists.
    """
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    old_view_360_key = product.view_360_key

    try:
        db.delete(product)
        db.commit()
        if old_view_360_key:
            delete_view_360_object(old_view_360_key)
        return
    except IntegrityError:
        db.rollback()

    product = db.get(Product, product_id)
    if not product:
        return

    suffix = f"-del-{product.id}"
    product.status = "deleted"
    product.view_360_url = None
    product.view_360_key = None
    if not (product.sku or "").endswith(suffix):
        product.sku = f"{(product.sku or 'sku')[: max(1, 40 - len(suffix))]}{suffix}"[:40]
    if product.product_id and not product.product_id.endswith(suffix):
        product.product_id = f"{product.product_id[: max(1, 40 - len(suffix))]}{suffix}"[:40]
    if not (product.slug or "").endswith(suffix):
        product.slug = f"{(product.slug or 'item')[: max(1, 220 - len(suffix))]}{suffix}"[:220]
    # Variants keep their rows (order/inventory history references them) but
    # their SKUs must be freed up too, or re-adding the same product later
    # collides with the "deleted" product's still-live variant SKUs.
    for variant in product.variants:
        if not (variant.sku or "").endswith(suffix):
            variant.sku = f"{(variant.sku or 'sku')[: max(1, 40 - len(suffix))]}{suffix}"[:40]
    try:
        db.commit()
        if old_view_360_key:
            delete_view_360_object(old_view_360_key)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete this product because it is still referenced by orders or inventory.",
        )
