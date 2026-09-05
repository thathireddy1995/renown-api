"""WhatsApp OTP for click-and-collect handover.

Same MSG91 `verify_user_v1` template as login. The store manager can mark a
package collected only after this code matches.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import IS_PRODUCTION, OTP_EXPIRY_MINUTES, OTP_MAX_ATTEMPTS
from app.core.ist import now as ist_now
from app.core.staff_users import digits_phone
from app.core.whatsapp_otp import WhatsAppOtpError, send_whatsapp_otp
from app.schemas import Customer, Order, OtpCode, StoreOrder

READY_STATUSES = {"ready"}
HANDOVER_STATUSES = {"collected"}


def pickup_otp_purpose(order: StoreOrder) -> str:
    return f"pk_{order.id}"


def _ten_digit(raw: str | None) -> str:
    phone = digits_phone(raw)
    if len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    return phone if len(phone) == 10 else ""


def customer_phone_10(db: Session, order: StoreOrder) -> str:
    """Resolve the customer's 10-digit mobile for this pickup order."""
    phone = _ten_digit(order.customer_phone)
    if phone:
        return phone

    if order.customer_id:
        customer = db.get(Customer, order.customer_id)
        phone = _ten_digit(customer.phone if customer else None)
        if phone:
            order.customer_phone = phone
            return phone

    web = db.scalar(select(Order).where(Order.order_number == order.order_number))
    if web:
        customer = db.get(Customer, web.customer_id) if web.customer_id else None
        phone = _ten_digit(customer.phone if customer else None)
        if phone:
            order.customer_phone = phone
            if order.customer_id is None:
                order.customer_id = web.customer_id
            return phone

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This order has no customer phone to send a pickup OTP.",
    )


def require_ready_pickup(order: StoreOrder) -> None:
    if (order.channel or "") != "click_collect":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pickup OTP is only for store collect orders.",
        )
    if (order.status or "").lower() not in READY_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Package must be marked ready for pickup before sending OTP.",
        )


def send_pickup_otp(db: Session, order: StoreOrder) -> tuple[str, int, str | None]:
    """Send WhatsApp OTP. Returns (message, expires_seconds, debug_otp)."""
    require_ready_pickup(order)
    phone = customer_phone_10(db, order)
    now = ist_now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpCode(
        phone=phone,
        code=code,
        purpose=pickup_otp_purpose(order),
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempt_count=0,
    )
    db.add(otp)
    db.flush()
    try:
        send_whatsapp_otp(phone, code)
    except WhatsAppOtpError:
        if IS_PRODUCTION:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send OTP. Try again.",
            )
    db.commit()
    return (
        "OTP sent to customer WhatsApp",
        OTP_EXPIRY_MINUTES * 60,
        None if IS_PRODUCTION else code,
    )


def consume_pickup_otp(db: Session, order: StoreOrder, code: str) -> None:
    """Raise unless `code` matches the latest unconsumed pickup OTP for this order."""
    require_ready_pickup(order)
    phone = customer_phone_10(db, order)
    now = ist_now()
    entered = (code or "").strip()
    if not entered:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter the customer OTP to hand over this package.",
        )

    purpose = pickup_otp_purpose(order)
    otp = db.scalar(
        select(OtpCode)
        .where(
            OtpCode.phone == phone,
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
            OtpCode.expires_at > now,
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
    )
    if not otp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No active pickup OTP. Send a new code to the customer.",
        )

    if otp.code != entered or otp.attempt_count >= OTP_MAX_ATTEMPTS:
        otp.attempt_count += 1
        db.commit()
        if otp.attempt_count >= OTP_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Too many incorrect attempts. Send a new OTP.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OTP. Ask the customer for the WhatsApp code.",
        )

    otp.consumed_at = now
    db.flush()
