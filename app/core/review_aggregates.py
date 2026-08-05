"""Batch helpers for product review averages / counts."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas import ProductReview


def review_aggregates_for(
    db: Session,
    product_ids: list[int],
) -> dict[int, tuple[float, int]]:
    """Return {product_id: (average_rating, review_count)} for approved reviews."""
    if not product_ids:
        return {}
    rows = db.execute(
        select(
            ProductReview.product_id,
            func.avg(ProductReview.rating),
            func.count(ProductReview.id),
        )
        .where(
            ProductReview.product_id.in_(product_ids),
            ProductReview.status == "approved",
        )
        .group_by(ProductReview.product_id)
    ).all()
    out: dict[int, tuple[float, int]] = {}
    for product_id, average, count in rows:
        out[int(product_id)] = (round(float(average or 0), 1), int(count or 0))
    return out
