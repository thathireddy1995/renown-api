"""Seed store POS orders from admin store-data mocks.

Run after seed_locations + seed_products (+ seed_inventory recommended):

    python -m scripts.seed_store_orders

Safe to re-run — matched by order_number.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import SessionLocal
from app.schemas import ProductVariant, Store, StoreOrder, StoreOrderItem

# order_number, store_code, customer, items_count, total, payment, associate, hours_ago, status, channel
ORDERS = [
    ("SO-4401", "ST-BLR-01", "Walk-in #421", 2, 24400, "card", "Rohan Bhatt", 8, "Completed", "in_store"),
    ("SO-4402", "ST-MUM-01", "Ananya Rao", 3, 41800, "upi", "Nisha Verma", 9, "Completed", "in_store"),
    ("SO-4403", "ST-BLR-02", "Walk-in #218", 1, 18900, "cash", "Kavya Rao", 10, "Completed", "in_store"),
    ("SO-4404", "ST-DEL-01", "Priya Nair", 2, 27600, "card", "Mira Sato", 11, "Refund pending", "in_store"),
    ("SO-4405", "ST-SIN-01", "Marcus Lee", 1, 21200, "card", "Kian Park", 12, "Completed", "in_store"),
    ("SO-4406", "ST-BLR-01", "Walk-in #422", 1, 9800, "upi", "Sanya Kapoor", 13, "Void", "in_store"),
    ("PU-9101", "ST-BLR-01", "Isla Fernández", 2, 18600, "online", None, 14, "Ready", "click_collect"),
    ("PU-9102", "ST-BLR-02", "Jonas Weber", 1, 12400, "online", None, 15, "Preparing", "click_collect"),
    ("PU-9103", "ST-MUM-01", "Ananya Rao", 3, 31200, "online", None, 40, "Collected", "click_collect"),
    ("PU-9104", "ST-SIN-01", "Marcus Lee", 1, 21200, "online", None, 16, "Ready", "click_collect"),
    ("PU-9105", "ST-DEL-01", "Priya Nair", 2, 15800, "online", None, 17, "Preparing", "click_collect"),
    ("PU-9106", "ST-BLR-01", "Elif Demir", 1, 9800, "online", None, 72, "Missed", "click_collect"),
]


def seed() -> None:
    db = SessionLocal()
    try:
        stores = {s.code: s for s in db.scalars(select(Store)).all()}
        if not stores:
            print("No stores — run seed_locations first")
            return
        variants = list(
            db.scalars(select(ProductVariant).order_by(ProductVariant.id).limit(20)).all()
        )
        if not variants:
            print("No variants — run seed_products first")
            return

        for (
            num,
            store_code,
            customer,
            items_n,
            total,
            payment,
            associate,
            hours_ago,
            status,
            channel,
        ) in ORDERS:
            store = stores.get(store_code) or next(iter(stores.values()))
            created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
            subtotal = Decimal(str(round(total / 1.18)))
            tax = Decimal(str(total)) - subtotal

            row = db.scalar(select(StoreOrder).where(StoreOrder.order_number == num))
            if row:
                row.store_id = store.id
                row.customer_name = customer
                row.channel = channel
                row.payment_method = payment
                row.associate_name = associate
                row.subtotal = subtotal
                row.tax = tax
                row.total = Decimal(str(total))
                row.status = status
                row.items.clear()
                db.flush()
            else:
                row = StoreOrder(
                    order_number=num,
                    store_id=store.id,
                    customer_name=customer,
                    channel=channel,
                    payment_method=payment,
                    associate_name=associate,
                    subtotal=subtotal,
                    tax=tax,
                    total=Decimal(str(total)),
                    status=status,
                    created_at=created,
                )
                db.add(row)
                db.flush()

            n = min(items_n, len(variants))
            unit = (subtotal / n).quantize(Decimal("0.01")) if n else Decimal("0")
            for i in range(n):
                db.add(
                    StoreOrderItem(
                        store_order_id=row.id,
                        variant_id=variants[i % len(variants)].id,
                        qty=1,
                        price_snapshot=unit,
                    )
                )
            print(f"Upserted {num}")

        db.commit()
        print("Store orders seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
