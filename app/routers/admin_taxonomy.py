"""Admin taxonomy CRUD — /admin/taxonomy/{categories,brands,collections,attributes}."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.taxonomy_utils import (
    ensure_slug,
    format_updated,
    public_id,
    status_label,
    status_store,
    type_label,
    type_store,
)
from app.database import get_db
from app.deps import pagination
from app.dto.taxonomy_dto import (
    AttributeCreate,
    AttributeListResponse,
    AttributeOut,
    AttributeUpdate,
    AttributeValueCreate,
    AttributeValueOut,
    TaxonomyCreate,
    TaxonomyListResponse,
    TaxonomyOut,
    TaxonomyUpdate,
)
from app.schemas import Attribute, AttributeValue, Brand, Category, Collection, Product

router = APIRouter(prefix="/admin/taxonomy", tags=["admin-taxonomy"])


def _product_counts_by_category(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Product.category_id, func.count())
        .where(Product.category_id.is_not(None))
        .group_by(Product.category_id)
    ).all()
    return {int(cid): int(n) for cid, n in rows if cid is not None}


def _product_counts_by_brand(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Product.brand_id, func.count())
        .where(Product.brand_id.is_not(None))
        .group_by(Product.brand_id)
    ).all()
    return {int(bid): int(n) for bid, n in rows if bid is not None}


def _taxonomy_out(row, products: int = 0) -> TaxonomyOut:
    return TaxonomyOut(
        id=public_id(row.id),
        name=row.name,
        slug=row.slug,
        products=products,
        status=status_label(row.status),
        updated=format_updated(row.updated_at),
    )


def _attr_out(row: Attribute) -> AttributeOut:
    return AttributeOut(
        id=public_id(row.id, "a"),
        name=row.name,
        type=type_label(row.type),
        values=[v.value for v in (row.values or [])],
    )


# ---- categories ----

@router.get("/categories", response_model=TaxonomyListResponse)
def list_categories(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> TaxonomyListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(Category)) or 0
    rows = db.scalars(
        select(Category).order_by(Category.id.asc()).limit(limit).offset(offset)
    ).all()
    counts = _product_counts_by_category(db)
    return TaxonomyListResponse(
        items=[_taxonomy_out(r, counts.get(r.id, 0)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/categories", response_model=TaxonomyOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: TaxonomyCreate, db: Session = Depends(get_db)) -> TaxonomyOut:
    slug = ensure_slug(payload.name, payload.slug)
    if db.scalar(select(Category).where(Category.slug == slug)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists.")
    row = Category(name=payload.name, slug=slug, status=status_store(payload.status))
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _taxonomy_out(row, 0)


@router.patch("/categories/{item_id}", response_model=TaxonomyOut)
def update_category(
    item_id: int, payload: TaxonomyUpdate, db: Session = Depends(get_db)
) -> TaxonomyOut:
    row = db.get(Category, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        data["status"] = status_store(data["status"])
    if "slug" in data and data["slug"]:
        data["slug"] = ensure_slug(data.get("name") or row.name, data["slug"])
    elif "name" in data and "slug" not in data:
        pass
    for k, v in data.items():
        setattr(row, k, v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    counts = _product_counts_by_category(db)
    return _taxonomy_out(row, counts.get(row.id, 0))


@router.delete("/categories/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Category, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---- brands ----

@router.get("/brands", response_model=TaxonomyListResponse)
def list_brands(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> TaxonomyListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(Brand)) or 0
    rows = db.scalars(select(Brand).order_by(Brand.id.asc()).limit(limit).offset(offset)).all()
    counts = _product_counts_by_brand(db)
    return TaxonomyListResponse(
        items=[_taxonomy_out(r, counts.get(r.id, 0)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/brands", response_model=TaxonomyOut, status_code=status.HTTP_201_CREATED)
def create_brand(payload: TaxonomyCreate, db: Session = Depends(get_db)) -> TaxonomyOut:
    slug = ensure_slug(payload.name, payload.slug)
    if db.scalar(select(Brand).where(Brand.slug == slug)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists.")
    row = Brand(name=payload.name, slug=slug, status=status_store(payload.status))
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _taxonomy_out(row, 0)


@router.patch("/brands/{item_id}", response_model=TaxonomyOut)
def update_brand(item_id: int, payload: TaxonomyUpdate, db: Session = Depends(get_db)) -> TaxonomyOut:
    row = db.get(Brand, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        data["status"] = status_store(data["status"])
    if "slug" in data and data["slug"]:
        data["slug"] = ensure_slug(data.get("name") or row.name, data["slug"])
    for k, v in data.items():
        setattr(row, k, v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    counts = _product_counts_by_brand(db)
    return _taxonomy_out(row, counts.get(row.id, 0))


@router.delete("/brands/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brand(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Brand, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---- collections ----

@router.get("/collections", response_model=TaxonomyListResponse)
def list_collections(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> TaxonomyListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(Collection)) or 0
    rows = db.scalars(
        select(Collection).order_by(Collection.id.asc()).limit(limit).offset(offset)
    ).all()
    return TaxonomyListResponse(
        items=[_taxonomy_out(r, 0) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/collections", response_model=TaxonomyOut, status_code=status.HTTP_201_CREATED)
def create_collection(payload: TaxonomyCreate, db: Session = Depends(get_db)) -> TaxonomyOut:
    slug = ensure_slug(payload.name, payload.slug)
    if db.scalar(select(Collection).where(Collection.slug == slug)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already exists.")
    row = Collection(name=payload.name, slug=slug, status=status_store(payload.status))
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _taxonomy_out(row, 0)


@router.patch("/collections/{item_id}", response_model=TaxonomyOut)
def update_collection(
    item_id: int, payload: TaxonomyUpdate, db: Session = Depends(get_db)
) -> TaxonomyOut:
    row = db.get(Collection, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        data["status"] = status_store(data["status"])
    if "slug" in data and data["slug"]:
        data["slug"] = ensure_slug(data.get("name") or row.name, data["slug"])
    for k, v in data.items():
        setattr(row, k, v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _taxonomy_out(row, 0)


@router.delete("/collections/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Collection, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---- attributes ----

@router.get("/attributes", response_model=AttributeListResponse)
def list_attributes(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> AttributeListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(Attribute)) or 0
    rows = db.scalars(
        select(Attribute)
        .options(selectinload(Attribute.values))
        .order_by(Attribute.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AttributeListResponse(
        items=[_attr_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/attributes", response_model=AttributeOut, status_code=status.HTTP_201_CREATED)
def create_attribute(payload: AttributeCreate, db: Session = Depends(get_db)) -> AttributeOut:
    if db.scalar(select(Attribute).where(Attribute.name == payload.name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Attribute already exists.")
    row = Attribute(name=payload.name, type=type_store(payload.type))
    db.add(row)
    db.flush()
    for val in payload.values:
        db.add(AttributeValue(attribute_id=row.id, value=val))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(Attribute).where(Attribute.id == row.id).options(selectinload(Attribute.values))
    )
    assert row is not None
    return _attr_out(row)


@router.patch("/attributes/{item_id}", response_model=AttributeOut)
def update_attribute(
    item_id: int, payload: AttributeUpdate, db: Session = Depends(get_db)
) -> AttributeOut:
    row = db.scalar(
        select(Attribute).where(Attribute.id == item_id).options(selectinload(Attribute.values))
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attribute not found.")
    data = payload.model_dump(exclude_unset=True)
    values = data.pop("values", None)
    if "type" in data and data["type"] is not None:
        data["type"] = type_store(data["type"])
    for k, v in data.items():
        setattr(row, k, v)
    if values is not None:
        row.values.clear()
        db.flush()
        for val in values:
            db.add(AttributeValue(attribute_id=row.id, value=val))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(Attribute).where(Attribute.id == item_id).options(selectinload(Attribute.values))
    )
    assert row is not None
    return _attr_out(row)


@router.delete("/attributes/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attribute(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Attribute, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attribute not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.post(
    "/attributes/{item_id}/values",
    response_model=AttributeValueOut,
    status_code=status.HTTP_201_CREATED,
)
def add_attribute_value(
    item_id: int, payload: AttributeValueCreate, db: Session = Depends(get_db)
) -> AttributeValueOut:
    row = db.get(Attribute, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attribute not found.")
    value = AttributeValue(attribute_id=item_id, value=payload.value)
    db.add(value)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(value)
    return AttributeValueOut.model_validate(value)


@router.delete(
    "/attributes/{item_id}/values/{value_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attribute_value(
    item_id: int, value_id: int, db: Session = Depends(get_db)
) -> None:
    value = db.scalar(
        select(AttributeValue).where(
            AttributeValue.id == value_id, AttributeValue.attribute_id == item_id
        )
    )
    if not value:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Value not found.")
    db.delete(value)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
