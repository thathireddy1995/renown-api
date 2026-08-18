"""Admin offers CRUD endpoints under /admin/offers."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.catalog_serialize import slugify
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.offers_dto import (
    OfferCreate,
    OfferListResponse,
    OfferOut,
    OfferUpdate,
)
from app.schemas import Brand, Category, Offer, Product

router = APIRouter(
    prefix="/admin/offers",
    tags=["admin-offers"],
    dependencies=[Depends(require_role("admin"))],
)


def _load_offer(db: Session, offer_id: int) -> Offer | None:
    """Load offer with relationships."""
    return db.scalar(
        select(Offer)
        .where(Offer.id == offer_id)
        .options(
            selectinload(Offer.product),
            selectinload(Offer.brand),
            selectinload(Offer.category),
        )
    )


def _determine_offer_status(offer: Offer) -> str:
    """Determine offer status based on dates and manual override.
    
    If status is manually set to 'inactive', keep it.
    Otherwise, determine based on current date:
    - Future start_date → 'scheduled'
    - Current date between start/end → 'active'
    - End date passed → 'expired'
    """
    if offer.status == "inactive":
        return "inactive"
    
    if offer.status == "deleted":
        return "deleted"
    
    now = datetime.now(offer.start_date.tzinfo)
    
    if now < offer.start_date:
        return "scheduled"
    elif now > offer.end_date:
        return "expired"
    else:
        return "active"


def _offer_out(offer: Offer) -> OfferOut:
    """Serialize Offer ORM to OfferOut DTO."""
    # Auto-determine status based on dates
    auto_status = _determine_offer_status(offer)
    
    return OfferOut(
        id=offer.id,
        name=offer.name,
        slug=offer.slug,
        discount_type=offer.discount_type,
        discount_value=float(offer.discount_value),
        maximum_discount=float(offer.maximum_discount) if offer.maximum_discount else None,
        apply_on=offer.apply_on,
        product_id=offer.product_id,
        product_name=offer.product.name if offer.product else None,
        brand_id=offer.brand_id,
        brand_name=offer.brand.name if offer.brand else None,
        category_id=offer.category_id,
        category_name=offer.category.name if offer.category else None,
        gender=offer.gender,
        start_date=offer.start_date,
        end_date=offer.end_date,
        priority=offer.priority,
        status=auto_status,
        created_at=offer.created_at,
        updated_at=offer.updated_at,
    )


@router.get("/", response_model=OfferListResponse)
def list_offers(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> OfferListResponse:
    """List offers with optional filters and search."""
    limit, offset = page
    stmt = select(Offer)
    count_stmt = select(func.count()).select_from(Offer)

    # Exclude soft-deleted offers
    stmt = stmt.where(Offer.status != "deleted")
    count_stmt = count_stmt.where(Offer.status != "deleted")

    # Filter by status
    if status_filter and status_filter != "all":
        # For status filters, we need to determine actual status based on dates
        if status_filter in ("scheduled", "active", "expired"):
            # Client filters by computed status; we'll filter client-side below
            pass
        elif status_filter == "inactive":
            stmt = stmt.where(Offer.status == "inactive")
            count_stmt = count_stmt.where(Offer.status == "inactive")

    # Search by name
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(Offer.name.ilike(like), Offer.slug.ilike(like)))
        count_stmt = count_stmt.where(or_(Offer.name.ilike(like), Offer.slug.ilike(like)))

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.options(
            selectinload(Offer.product),
            selectinload(Offer.brand),
            selectinload(Offer.category),
        )
        .order_by(Offer.priority.desc(), Offer.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    # Apply computed status filter on client side (after date determination)
    items = [_offer_out(o) for o in rows]
    if status_filter and status_filter != "all" and status_filter != "inactive":
        items = [o for o in items if o.status == status_filter]

    return OfferListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{offer_id}", response_model=OfferOut)
def get_offer(offer_id: int, db: Session = Depends(get_db)) -> OfferOut:
    """Get a single offer."""
    offer = _load_offer(db, offer_id)
    if not offer or offer.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")
    return _offer_out(offer)


@router.post("/", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
def create_offer(payload: OfferCreate, db: Session = Depends(get_db)) -> OfferOut:
    """Create a new offer."""
    # Validate that end_date > start_date
    if payload.end_date <= payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="End date must be after start date.",
        )

    # Validate based on apply_on
    if payload.apply_on == "PRODUCT" and not payload.product_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Product ID is required when applying to a product.",
        )
    if payload.apply_on == "BRAND" and not payload.brand_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Brand ID is required when applying to a brand.",
        )
    if payload.apply_on == "CATEGORY" and not payload.category_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Category ID is required when applying to a category.",
        )
    if payload.apply_on == "GENDER" and not payload.gender:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gender is required when applying to a gender segment.",
        )

    # Validate max discount for percentage offers
    if payload.discount_type == "PERCENTAGE" and payload.discount_value > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Discount value cannot exceed 100% for percentage-based offers.",
        )

    slug = _unique_offer_slug(db, payload.name)

    offer = Offer(
        name=payload.name,
        slug=slug,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        maximum_discount=payload.maximum_discount,
        apply_on=payload.apply_on,
        product_id=payload.product_id,
        brand_id=payload.brand_id,
        category_id=payload.category_id,
        gender=payload.gender,
        start_date=payload.start_date,
        end_date=payload.end_date,
        priority=payload.priority,
        status="scheduled",  # Will be auto-determined on retrieval
    )

    db.add(offer)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An offer with this name or slug already exists.",
        ) from e
    except DataError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid data for offer fields. {err.orig}",
        ) from err

    offer = _load_offer(db, offer.id)
    assert offer is not None
    return _offer_out(offer)


@router.patch("/{offer_id}", response_model=OfferOut)
def update_offer(
    offer_id: int, payload: OfferUpdate, db: Session = Depends(get_db)
) -> OfferOut:
    """Update an offer."""
    offer = _load_offer(db, offer_id)
    if not offer or offer.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")

    data = payload.model_dump(exclude_unset=True)

    # Validate dates if provided
    start_date = data.get("start_date", offer.start_date)
    end_date = data.get("end_date", offer.end_date)
    if end_date <= start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="End date must be after start date.",
        )

    # Validate apply_on constraints
    apply_on = data.get("apply_on", offer.apply_on)
    if apply_on == "PRODUCT" and not data.get("product_id", offer.product_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Product ID is required when applying to a product.",
        )
    if apply_on == "BRAND" and not data.get("brand_id", offer.brand_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Brand ID is required when applying to a brand.",
        )
    if apply_on == "CATEGORY" and not data.get("category_id", offer.category_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Category ID is required when applying to a category.",
        )
    if apply_on == "GENDER" and not data.get("gender", offer.gender):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Gender is required when applying to a gender segment.",
        )

    # Validate percentage offers
    discount_type = data.get("discount_type", offer.discount_type)
    discount_value = data.get("discount_value", offer.discount_value)
    if discount_type == "PERCENTAGE" and discount_value > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Discount value cannot exceed 100% for percentage-based offers.",
        )

    # Update fields
    for key, value in data.items():
        if hasattr(offer, key):
            setattr(offer, key, value)

    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An offer with this name or slug already exists.",
        ) from e
    except DataError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid data for offer fields. {err.orig}",
        ) from err

    offer = _load_offer(db, offer.id)
    assert offer is not None
    return _offer_out(offer)


@router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_offer(offer_id: int, db: Session = Depends(get_db)) -> None:
    """Soft-delete an offer by setting status to 'deleted'."""
    offer = db.get(Offer, offer_id)
    if not offer or offer.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")

    # Soft delete: set status to deleted
    offer.status = "deleted"
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete offer.",
        ) from e


@router.post("/{offer_id}/activate", response_model=OfferOut)
def activate_offer(offer_id: int, db: Session = Depends(get_db)) -> OfferOut:
    """Activate an offer (set status to match computed status, not forced to 'active')."""
    offer = _load_offer(db, offer_id)
    if not offer or offer.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")

    # Reset status to let auto-determination happen
    offer.status = "active"

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate offer.",
        ) from e

    offer = _load_offer(db, offer.id)
    assert offer is not None
    return _offer_out(offer)


@router.post("/{offer_id}/deactivate", response_model=OfferOut)
def deactivate_offer(offer_id: int, db: Session = Depends(get_db)) -> OfferOut:
    """Deactivate an offer (set status to 'inactive')."""
    offer = _load_offer(db, offer_id)
    if not offer or offer.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")

    offer.status = "inactive"

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate offer.",
        ) from e

    offer = _load_offer(db, offer.id)
    assert offer is not None
    return _offer_out(offer)


def _unique_offer_slug(db: Session, base_name: str, exclude_id: int | None = None) -> str:
    """Generate a unique slug for an offer."""
    slug = slugify(base_name)[:220]
    suffix_n = 2
    while True:
        stmt = select(Offer.id).where(Offer.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(Offer.id != exclude_id)
        if not db.scalar(stmt):
            return slug
        suffix = f"-{suffix_n}"
        slug = f"{slugify(base_name)[: 220 - len(suffix)]}{suffix}"
        suffix_n += 1
