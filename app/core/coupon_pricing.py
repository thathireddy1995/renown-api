"""Quote and redeem checkout coupons against the current cart."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.ist import as_ist, now as ist_now
from app.core.offer_pricing import _gender_key
from app.schemas import CartItem, Coupon, CouponRedemption, Product


@dataclass(frozen=True)
class CouponQuote:
    coupon: Coupon
    code: str
    discount: Decimal
    eligible_subtotal: Decimal
    label: str


def _aware(dt: datetime) -> datetime:
    return as_ist(dt)


def _status_for_dates(start_date: datetime, end_date: datetime) -> str:
    current = ist_now()
    if current < _aware(start_date):
        return "scheduled"
    if current > _aware(end_date):
        return "expired"
    return "active"


def _live_status(coupon: Coupon) -> str:
    if coupon.status in ("inactive", "deleted"):
        return coupon.status
    return _status_for_dates(coupon.start_date, coupon.end_date)


def _applies_to_product(coupon: Coupon, product: Product | None) -> bool:
    if product is None:
        return False
    if coupon.apply_on == "ALL":
        return True
    if coupon.apply_on == "BRAND":
        return coupon.brand_id is not None and coupon.brand_id == product.brand_id
    if coupon.apply_on == "CATEGORY":
        return coupon.category_id is not None and coupon.category_id == product.category_id
    if coupon.apply_on == "GENDER":
        return _gender_key(coupon.gender) == _gender_key(product.gender)
    return False


def _eligible_subtotal(
    coupon: Coupon, line_rows: list[tuple[CartItem, Decimal]]
) -> Decimal:
    total = Decimal("0")
    for row, unit in line_rows:
        if _applies_to_product(coupon, row.product):
            total += unit * Decimal(row.qty)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _discount_for(coupon: Coupon, eligible: Decimal) -> Decimal:
    if eligible <= 0:
        return Decimal("0")
    if coupon.discount_type == "PERCENTAGE":
        discount = eligible * Decimal(coupon.discount_value) / Decimal("100")
        if coupon.maximum_discount is not None:
            discount = min(discount, Decimal(coupon.maximum_discount))
    else:
        discount = Decimal(coupon.discount_value)
    return min(eligible, discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _label(coupon: Coupon) -> str:
    if coupon.discount_type == "PERCENTAGE":
        return f"{Decimal(coupon.discount_value):g}% OFF"
    return f"₹{Decimal(coupon.discount_value):g} OFF"


def _customer_redemptions(db: Session, coupon_id: int, customer_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(CouponRedemption)
            .where(
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.customer_id == customer_id,
            )
        )
        or 0
    )


def _load_live_coupon(db: Session, code: str, *, for_update: bool = False) -> Coupon:
    normalized = (code or "").strip().upper()
    stmt = (
        select(Coupon)
        .where(func.upper(Coupon.code) == normalized, Coupon.status != "deleted")
        .options(selectinload(Coupon.brand), selectinload(Coupon.category))
    )
    if for_update:
        stmt = stmt.with_for_update()
    coupon = db.scalar(stmt)
    if not coupon:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid coupon code.",
        )
    live = _live_status(coupon)
    if live == "inactive":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon is not active.",
        )
    if live == "scheduled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon is not valid yet.",
        )
    if live == "expired":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon has expired.",
        )
    return coupon


def quote_coupon(
    db: Session,
    code: str,
    customer_id: int,
    line_rows: list[tuple[CartItem, Decimal]],
    cart_subtotal: Decimal,
    *,
    for_update: bool = False,
) -> CouponQuote:
    coupon = _load_live_coupon(db, code, for_update=for_update)

    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon has reached its usage limit.",
        )
    if coupon.per_customer_limit is not None:
        used = _customer_redemptions(db, coupon.id, customer_id)
        if used >= coupon.per_customer_limit:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already used this coupon.",
            )

    min_order = Decimal(coupon.min_order_amount or 0)
    if cart_subtotal < min_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum order of ₹{min_order:g} required for this coupon.",
        )

    eligible = _eligible_subtotal(coupon, line_rows)
    if eligible <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon does not apply to items in your cart.",
        )

    discount = _discount_for(coupon, eligible)
    if discount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This coupon does not apply to items in your cart.",
        )

    return CouponQuote(
        coupon=coupon,
        code=coupon.code,
        discount=discount,
        eligible_subtotal=eligible,
        label=_label(coupon),
    )


def redeem_coupon(
    db: Session,
    code: str,
    customer_id: int,
    order_id: int,
    line_rows: list[tuple[CartItem, Decimal]],
    cart_subtotal: Decimal,
) -> CouponQuote:
    quoted = quote_coupon(
        db, code, customer_id, line_rows, cart_subtotal, for_update=True
    )
    quoted.coupon.used_count = int(quoted.coupon.used_count or 0) + 1
    db.add(
        CouponRedemption(
            coupon_id=quoted.coupon.id,
            customer_id=customer_id,
            order_id=order_id,
            discount_amount=quoted.discount,
        )
    )
    return quoted
