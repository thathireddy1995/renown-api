"""Admin catalog — variants CRUD under /admin/catalog/variants."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.catalog_serialize import variant_out
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.catalog_dto import (
    ProductVariantCreate,
    ProductVariantOut,
    ProductVariantUpdate,
    VariantListResponse,
)
from app.schemas import Product, ProductVariant

router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog-variants"], dependencies=[Depends(require_role("admin"))])


@router.get("/variants", response_model=VariantListResponse)
def list_variants(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    product_id: int | None = Query(None),
) -> VariantListResponse:
    limit, offset = page
    stmt = select(ProductVariant).options(selectinload(ProductVariant.product))
    count_stmt = select(func.count()).select_from(ProductVariant)

    if product_id is not None:
        stmt = stmt.where(ProductVariant.product_id == product_id)
        count_stmt = count_stmt.where(ProductVariant.product_id == product_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(ProductVariant.id.asc()).limit(limit).offset(offset)
    ).all()

    return VariantListResponse(
        items=[variant_out(v, v.product.name if v.product else "") for v in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/variants", response_model=ProductVariantOut, status_code=status.HTTP_201_CREATED)
def create_variant(
    payload: ProductVariantCreate, db: Session = Depends(get_db)
) -> ProductVariantOut:
    if payload.product_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="product_id is required.",
        )
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    existing = db.scalar(select(ProductVariant).where(ProductVariant.sku == payload.sku))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A variant with this SKU already exists.",
        )

    variant = ProductVariant(
        product_id=payload.product_id,
        sku=payload.sku,
        color=payload.color,
        color_hex=payload.color_hex,
        size=payload.size,
        price=payload.price if payload.price is not None else product.price,
        stock=payload.stock,
    )
    db.add(variant)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(variant)
    return variant_out(variant, product.name)


@router.patch("/variants/{variant_id}", response_model=ProductVariantOut)
def update_variant(
    variant_id: int, payload: ProductVariantUpdate, db: Session = Depends(get_db)
) -> ProductVariantOut:
    variant = db.scalar(
        select(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .options(selectinload(ProductVariant.product))
    )
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")

    data = payload.model_dump(exclude_unset=True)
    if "product_id" in data and data["product_id"] is not None:
        product = db.get(Product, data["product_id"])
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    for key, value in data.items():
        setattr(variant, key, value)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    variant = db.scalar(
        select(ProductVariant)
        .where(ProductVariant.id == variant_id)
        .options(selectinload(ProductVariant.product))
    )
    assert variant is not None
    return variant_out(variant, variant.product.name if variant.product else "")


@router.delete("/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_variant(variant_id: int, db: Session = Depends(get_db)) -> None:
    variant = db.get(ProductVariant, variant_id)
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found.")
    db.delete(variant)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
