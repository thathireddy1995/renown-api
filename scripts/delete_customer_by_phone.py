"""One-off: delete a customer by phone (and related rows / OTPs).

Usage (from renown-api root, with venv + .env):

    python -m scripts.delete_customer_by_phone 7845550512
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select

from app.database import SessionLocal
from app.schemas import Customer, Order, OtpCode


def normalize_phone(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10:
        raise SystemExit(f"Expected a 10-digit mobile, got: {raw!r}")
    return digits


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m scripts.delete_customer_by_phone <10-digit-phone>")

    phone = normalize_phone(sys.argv[1])
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.phone == phone))
        if not customer:
            otp_count = db.scalar(
                select(func.count()).select_from(OtpCode).where(OtpCode.phone == phone)
            ) or 0
            if otp_count:
                db.execute(delete(OtpCode).where(OtpCode.phone == phone))
                db.commit()
                print(f"No customer for {phone}; deleted {otp_count} OTP row(s).")
            else:
                print(f"No customer or OTPs found for {phone}.")
            return

        cid = customer.id
        order_count = db.scalar(
            select(func.count()).select_from(Order).where(Order.customer_id == cid)
        ) or 0
        otp_count = db.scalar(
            select(func.count()).select_from(OtpCode).where(OtpCode.phone == phone)
        ) or 0

        print(
            f"Deleting customer id={cid} name={customer.name!r} phone={phone} "
            f"(orders={order_count}, otps={otp_count})"
        )

        # Orders / cart / wishlist / addresses / prescriptions CASCADE from customers.
        db.execute(delete(OtpCode).where(OtpCode.phone == phone))
        db.delete(customer)
        db.commit()
        print("Done. You can register again with this number.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
