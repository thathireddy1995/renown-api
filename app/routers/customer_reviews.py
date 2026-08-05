"""Verified-purchase product reviews for the customer storefront."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.product_resolve import resolve_product
from app.database import get_db
from app.deps import get_current_customer, pagination
from app.dto.review_dto import (
    ReviewCreateRequest,
    ReviewEligibilityResponse,
    ReviewImageOut,
    ReviewListResponse,
    ReviewOut,
)
from app.schemas import (
    Customer,
    Order,
    OrderItem,
    ProductReview,
    ProductReviewImage,
)

router = APIRouter(prefix="/customer/products", tags=["customer-reviews"])

MAX_IMAGES = 3
# Keep well under API Gateway / Lambda sync payload limits when clients send
# base64 data URLs (3 images × this cap must remain comfortably under 6MB).
MAX_IMAGE_URL_LEN = 400_000
_ALLOWED_DATA_IMAGE_PREFIXES = (
    "data:image/jpeg;base64,",
    "data:image/jpg;base64,",
    "data:image/png;base64,",
    "data:image/webp;base64,",
    "data:image/gif;base64,",
)


def _public_author_name(customer: Customer | None) -> str:
    raw = (customer.name or "").strip() if customer else ""
    if not raw:
        return "Customer"
    parts = raw.split()
    first = parts[0].capitalize()
    if len(parts) == 1:
        return first
    return f"{first} {parts[-1][0].upper()}."


def _validate_image_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review image URL is required.",
        )
    if len(value) > MAX_IMAGE_URL_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review image is too large. Use a smaller photo.",
        )
    if value.startswith("https://"):
        return value
    lowered = value.lower()
    if any(lowered.startswith(prefix) for prefix in _ALLOWED_DATA_IMAGE_PREFIXES):
        return value
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Review images must be HTTPS URLs or JPEG/PNG/WebP/GIF data URLs.",
    )


def _delivered_order_id(db: Session, customer_id: int, product_id: int) -> int | None:
    return db.scalar(
        select(Order.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(
            Order.customer_id == customer_id,
            OrderItem.product_id == product_id,
            func.lower(Order.status) == "delivered",
        )
        .order_by(Order.id.desc())
        .limit(1)
    )


def _existing_review_id(db: Session, customer_id: int, product_id: int) -> int | None:
    return db.scalar(
        select(ProductReview.id).where(
            ProductReview.customer_id == customer_id,
            ProductReview.product_id == product_id,
        )
    )


def _review_out(review: ProductReview) -> ReviewOut:
    return ReviewOut(
        id=review.id,
        rating=review.rating,
        title=review.title,
        body=review.body,
        author_name=_public_author_name(review.customer),
        verified_purchase=True,
        images=[
            ReviewImageOut(id=img.id, url=img.url, sort_order=img.sort_order)
            for img in (review.images or [])
        ],
        created_at=review.created_at,
    )


def _aggregates(db: Session, product_id: int) -> tuple[float, int, dict[str, int]]:
    rows = db.execute(
        select(ProductReview.rating, func.count())
        .where(
            ProductReview.product_id == product_id,
            ProductReview.status == "approved",
        )
        .group_by(ProductReview.rating)
    ).all()
    breakdown = {str(i): 0 for i in range(1, 6)}
    total = 0
    weighted = 0.0
    for rating, count in rows:
        key = str(int(rating))
        n = int(count)
        breakdown[key] = n
        total += n
        weighted += float(rating) * n
    average = round(weighted / total, 1) if total else 0.0
    return average, total, breakdown


@router.get("/{slug}/reviews", response_model=ReviewListResponse)
def list_reviews(
    slug: str,
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> ReviewListResponse:
    product = resolve_product(db, slug)
    limit, offset = page
    average, total, breakdown = _aggregates(db, product.id)
    rows = db.scalars(
        select(ProductReview)
        .where(
            ProductReview.product_id == product.id,
            ProductReview.status == "approved",
        )
        .options(
            selectinload(ProductReview.images),
            selectinload(ProductReview.customer),
        )
        .order_by(ProductReview.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ReviewListResponse(
        items=[_review_out(r) for r in rows],
        total=total,
        average_rating=average,
        rating_breakdown=breakdown,
        limit=limit,
        offset=offset,
    )


@router.get("/{slug}/reviews/eligibility", response_model=ReviewEligibilityResponse)
def review_eligibility(
    slug: str,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> ReviewEligibilityResponse:
    product = resolve_product(db, slug)
    if _existing_review_id(db, customer.id, product.id):
        return ReviewEligibilityResponse(
            can_review=False,
            reason="You have already reviewed this product.",
            already_reviewed=True,
            has_delivered_purchase=True,
        )
    order_id = _delivered_order_id(db, customer.id, product.id)
    if not order_id:
        return ReviewEligibilityResponse(
            can_review=False,
            reason="Only customers with a delivered order can review this product.",
            already_reviewed=False,
            has_delivered_purchase=False,
        )
    return ReviewEligibilityResponse(
        can_review=True,
        reason=None,
        already_reviewed=False,
        has_delivered_purchase=True,
    )


@router.post("/{slug}/reviews", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    slug: str,
    payload: ReviewCreateRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> ReviewOut:
    product = resolve_product(db, slug)
    if _existing_review_id(db, customer.id, product.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this product.",
        )
    order_id = _delivered_order_id(db, customer.id, product.id)
    if not order_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customers with a delivered order can review this product.",
        )

    body = payload.body.strip()
    if len(body) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review text must be at least 10 characters.",
        )
    title = (payload.title or "").strip() or None
    images = payload.images[:MAX_IMAGES]
    validated_urls = [_validate_image_url(img.url) for img in images]

    review = ProductReview(
        product_id=product.id,
        customer_id=customer.id,
        order_id=order_id,
        rating=payload.rating,
        title=title,
        body=body,
        status="approved",
    )
    db.add(review)
    try:
        db.flush()
        for index, url in enumerate(validated_urls):
            db.add(ProductReviewImage(review_id=review.id, url=url, sort_order=index))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already reviewed this product.",
        ) from None

    loaded = db.scalar(
        select(ProductReview)
        .where(ProductReview.id == review.id)
        .options(
            selectinload(ProductReview.images),
            selectinload(ProductReview.customer),
        )
    )
    assert loaded is not None
    return _review_out(loaded)
