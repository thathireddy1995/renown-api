"""Customer online payments — /customer/payments (JWT required).

Typical ecommerce flow: the cart is priced and a Razorpay order is opened
(create-order), the customer pays in the Razorpay checkout widget, and only
on a verified + captured payment does an Order row get written (verify).
A failed/cancelled/tampered payment never creates an order. Cash-on-delivery
skips this router entirely and goes straight through /customer/orders.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import RAZORPAY_KEY_ID
from app.core.customer_prescription import upsert_from_cart_lines
from app.core.order_service import (
    compute_pricing,
    create_order_record,
    load_cart_lines,
    resolve_pickup_store,
    resolve_shipping_address,
)
from app.core.payments import (
    MIN_AMOUNT_PAISE,
    RazorpayAuthError,
    RazorpayOrderError,
    create_razorpay_order,
    fetch_payment,
    verify_payment_signature,
)
from app.core.shiprocket_fulfill import attach_shiprocket_shipment
from app.database import get_db
from app.deps import get_current_customer
from app.dto.order_dto import OrderOut
from app.dto.payment_dto import (
    CreatePaymentOrderRequest,
    CreatePaymentOrderResponse,
    VerifyPaymentRequest,
)
from app.routers.customer_orders import _order_items_eager, _order_out
from app.routers.telegram_notify import notify_order_placed
from app.schemas import Customer, Order

router = APIRouter(prefix="/customer/payments", tags=["customer-payments"])


@router.post("/create-order", response_model=CreatePaymentOrderResponse)
def create_payment_order(
    payload: CreatePaymentOrderRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CreatePaymentOrderResponse:
    """Price the current cart and open a Razorpay order for that amount.
    No local Order row is written yet — that only happens in /verify."""
    if not (RAZORPAY_KEY_ID or "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Online payments are not configured.",
        )

    _line_rows, subtotal = load_cart_lines(db, customer)
    delivery = payload.delivery or "ship"
    resolve_shipping_address(db, customer, payload.address_id, delivery)
    resolve_pickup_store(db, delivery, payload.pickup_store_id)

    _discount, _shipping, _tax, total, _coupon = compute_pricing(
        subtotal, delivery, payload.coupon_code, db=db, customer=customer, line_rows=_line_rows
    )
    amount_paise = int((total * 100).to_integral_value())
    if amount_paise < MIN_AMOUNT_PAISE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum payable amount is ₹{MIN_AMOUNT_PAISE / 100:.0f}.",
        )

    try:
        rzp_order = create_razorpay_order(
            amount_paise=amount_paise,
            receipt=f"cust-{customer.id}-{int(time.time() * 1000)}",
            notes={
                "customer_id": str(customer.id),
                "coupon_code": _coupon or "",
            },
        )
    except RazorpayAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except (RazorpayOrderError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return CreatePaymentOrderResponse(
        razorpay_order_id=rzp_order["id"],
        amount=amount_paise,
        currency=rzp_order.get("currency") or "INR",
        razorpay_key=RAZORPAY_KEY_ID,
        amount_display=float(total),
    )


@router.post("/verify", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def verify_payment(
    payload: VerifyPaymentRequest,
    response: Response,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderOut:
    """Verify the Razorpay signature + capture status, then place the order.
    Anything less than a captured, signature-valid payment raises — the
    frontend must treat any error here as "order not placed"."""
    if not (
        payload.razorpay_order_id
        and payload.razorpay_payment_id
        and payload.razorpay_signature
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing payment fields. Order was not placed.",
        )

    # Idempotent retry: same payment must not create a second order.
    existing = db.scalar(
        select(Order)
        .where(
            Order.razorpay_payment_id == payload.razorpay_payment_id,
            Order.customer_id == customer.id,
        )
        .options(*_order_items_eager())
    )
    if existing:
        response.status_code = status.HTTP_200_OK
        return _order_out(existing, db)

    try:
        ok = verify_payment_signature(
            razorpay_order_id=payload.razorpay_order_id,
            razorpay_payment_id=payload.razorpay_payment_id,
            razorpay_signature=payload.razorpay_signature,
        )
    except RazorpayAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed. Order was not placed.",
        )

    try:
        payment = fetch_payment(payload.razorpay_payment_id)
    except Exception as exc:  # noqa: BLE001 — surface Razorpay fetch failures cleanly
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not confirm payment with Razorpay: {exc}",
        ) from exc

    if payment.get("status") != "captured":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment not completed (status: {payment.get('status')}). Order was not placed.",
        )

    line_rows, subtotal = load_cart_lines(db, customer)
    delivery = payload.delivery or "ship"
    address_id = resolve_shipping_address(db, customer, payload.address_id, delivery)

    # Snapshot Rx onto the customer profile before create_order_record commits
    # and deletes cart rows (expired CartItem.lens_fit would fail after that).
    upsert_from_cart_lines(db, customer.id, line_rows)
    try:
        order = create_order_record(
            db,
            customer,
            address_id=address_id,
            delivery=delivery,
            pickup_store_id=payload.pickup_store_id,
            coupon_code=payload.coupon_code,
            line_rows=line_rows,
            subtotal=subtotal,
            payment_method="razorpay",
            payment_status="paid",
            razorpay_order_id=payload.razorpay_order_id,
            razorpay_payment_id=payload.razorpay_payment_id,
        )
    except IntegrityError:
        # Concurrent verify with the same payment id — return the winner.
        db.rollback()
        raced = db.scalar(
            select(Order)
            .where(
                Order.razorpay_payment_id == payload.razorpay_payment_id,
                Order.customer_id == customer.id,
            )
            .options(*_order_items_eager())
        )
        if raced:
            response.status_code = status.HTTP_200_OK
            return _order_out(raced, db)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment already processed but order could not be loaded.",
        )

    attach_shiprocket_shipment(db, order, customer)
    db.refresh(order)
    notify_order_placed(order, customer)

    # Re-load with eager options for a stable OrderOut (items/products).
    order = db.scalar(
        select(Order).where(Order.id == order.id).options(*_order_items_eager())
    )
    assert order is not None
    return _order_out(order, db)
