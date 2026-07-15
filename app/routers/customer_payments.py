"""Customer online payments — /customer/payments (JWT required).

Typical ecommerce flow: the cart is priced and a Razorpay order is opened
(create-order), the customer pays in the Razorpay checkout widget, and only
on a verified + captured payment does an Order row get written (verify).
A failed/cancelled/tampered payment never creates an order. Cash-on-delivery
skips this router entirely and goes straight through /customer/orders.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import RAZORPAY_KEY_ID
from app.core.order_service import (
    compute_pricing,
    create_order_record,
    load_cart_lines,
    resolve_shipping_address,
)
from app.core.payments import client as razorpay_client
from app.core.payments import errors as razorpay_errors
from app.database import get_db
from app.deps import get_current_customer
from app.dto.order_dto import OrderOut
from app.dto.payment_dto import (
    CreatePaymentOrderRequest,
    CreatePaymentOrderResponse,
    VerifyPaymentRequest,
)
from app.routers.customer_orders import _order_out
from app.schemas import Customer

router = APIRouter(prefix="/customer/payments", tags=["customer-payments"])


@router.post("/create-order", response_model=CreatePaymentOrderResponse)
def create_payment_order(
    payload: CreatePaymentOrderRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CreatePaymentOrderResponse:
    """Price the current cart and open a Razorpay order for that amount.
    No local Order row is written yet — that only happens in /verify."""
    _line_rows, subtotal = load_cart_lines(db, customer)
    resolve_shipping_address(db, customer, payload.address_id, payload.delivery or "ship")

    _discount, _shipping, _tax, total, _coupon = compute_pricing(
        subtotal, payload.delivery or "ship", payload.coupon_code
    )
    amount_paise = int((total * 100).to_integral_value())
    if amount_paise <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to pay.")

    try:
        rzp_order = razorpay_client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"cust-{customer.id}-{int(time.time() * 1000)}",
                "payment_capture": 1,
                "notes": {"customer_id": str(customer.id)},
            }
        )
    except razorpay_errors.BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return CreatePaymentOrderResponse(
        razorpay_order_id=rzp_order["id"],
        amount=amount_paise,
        currency="INR",
        razorpay_key=RAZORPAY_KEY_ID,
        amount_display=float(total),
    )


@router.post("/verify", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def verify_payment(
    payload: VerifyPaymentRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderOut:
    """Verify the Razorpay signature + capture status, then place the order.
    Anything less than a captured, signature-valid payment raises — the
    frontend must treat any error here as "order not placed"."""
    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except razorpay_errors.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed. Order was not placed.",
        )

    payment = razorpay_client.payment.fetch(payload.razorpay_payment_id)
    if payment.get("status") != "captured":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not completed (status: {payment.get('status')}). Order was not placed.",
        )

    line_rows, subtotal = load_cart_lines(db, customer)
    address_id = resolve_shipping_address(db, customer, payload.address_id, payload.delivery or "ship")

    order = create_order_record(
        db,
        customer,
        address_id=address_id,
        delivery=payload.delivery or "ship",
        coupon_code=payload.coupon_code,
        line_rows=line_rows,
        subtotal=subtotal,
        payment_method="razorpay",
        payment_status="paid",
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
    )
    return _order_out(order)
