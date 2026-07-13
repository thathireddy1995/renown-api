"""Seed demo customers for OTP auth QA.

Run after migrations/0002_create_customers_table.sql:

    source venv/bin/activate
    python -m scripts.seed_customers

Safe to re-run — existing customers are updated in place (matched by phone).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import SessionLocal
from app.schemas import Customer

SEED_CUSTOMERS = [
    {
        "name": "Demo Customer One",
        "phone": "9000000001",
        "email": "demo1@renowneyewear.com",
    },
    {
        "name": "Demo Customer Two",
        "phone": "9000000002",
        "email": "demo2@renowneyewear.com",
    },
    {
        "name": "Demo Customer Three",
        "phone": "9000000003",
        "email": "demo3@renowneyewear.com",
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        for row in SEED_CUSTOMERS:
            existing = db.scalar(select(Customer).where(Customer.phone == row["phone"]))
            if existing:
                existing.name = row["name"]
                existing.email = row["email"]
                existing.is_active = True
                print(f"Updated: {row['phone']} ({row['name']})")
            else:
                db.add(
                    Customer(
                        name=row["name"],
                        phone=row["phone"],
                        email=row["email"],
                        is_active=True,
                    )
                )
                print(f"Created: {row['phone']} ({row['name']})")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
