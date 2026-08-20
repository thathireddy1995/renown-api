"""Customer coupon validation under /customer/coupons."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.coupon_pricing import quote_coupon
from app.core.order_service import load_cart_lines
from app.database import get_db
from app.deps import get_current_customer
from app.dto.coupons_dto import CouponValidateRequest, CouponValidateResponse
from app.schemas import Customer

router = APIRouter(prefix="/customer/coupons", tags=["customer-coupons"])


@router.post("/validate", response_model=CouponValidateResponse)
def validate_coupon(
    payload: CouponValidateRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CouponValidateResponse:
    line_rows, subtotal = load_cart_lines(db, customer)
    quoted = quote_coupon(db, payload.code, customer.id, line_rows, subtotal)
    return CouponValidateResponse(
        code=quoted.code,
        name=quoted.coupon.name,
        discount=quoted.discount,
        discount_type=quoted.coupon.discount_type,
        discount_value=quoted.coupon.discount_value,
        label=quoted.label,
        eligible_subtotal=quoted.eligible_subtotal,
    )
