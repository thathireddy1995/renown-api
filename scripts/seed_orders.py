"""Seed two demo orders (RO-83291 delivered, RO-83402 shipped).

Run after migrations 0016–0018 and product/customer seeds:

    python -m scripts.seed_orders

Safe to re-run — matched by order_number.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import SessionLocal
from app.schemas import Address, Customer, Order, OrderItem, Product

DEMO_PHONE = "9000000001"

ORDERS = [
    {
        "order_number": "RO-83291",
        "status": "delivered",
        "days_ago": 29,
        "items": [("ADM-HAL-001", 1), ("RO-1000", 1)],
    },
    {
        "order_number": "RO-83402",
        "status": "shipped",
        "days_ago": 15,
        "items": [("ADM-MAR-002", 1)],
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        customer = db.scalar(select(Customer).where(Customer.phone == DEMO_PHONE))
        if not customer:
            customer = Customer(
                name="Demo Customer One",
                phone=DEMO_PHONE,
                email="demo1@renowneyewear.com",
                is_active=True,
            )
            db.add(customer)
            db.flush()
            print(f"Created demo customer {DEMO_PHONE}")

        address = db.scalar(
            select(Address).where(Address.customer_id == customer.id).limit(1)
        )
        if not address:
            address = Address(
                customer_id=customer.id,
                label="Home",
                line1="42 Redchurch St",
                city="London",
                postal_code="E2 7DP",
                country="UK",
                phone="+44 20 7946 0018",
                is_default=True,
            )
            db.add(address)
            db.flush()
            print("Created demo address")

        products_by_sku = {
            p.sku: p for p in db.scalars(select(Product)).all()
        }
        # Fallback: any products if specific SKUs missing
        any_products = list(products_by_sku.values())

        for spec in ORDERS:
            existing = db.scalar(
                select(Order)
                .where(Order.order_number == spec["order_number"])
                .options(selectinload(Order.items))
            )
            created_at = datetime.now(timezone.utc) - timedelta(days=spec["days_ago"])

            line_defs = []
            for sku, qty in spec["items"]:
                product = products_by_sku.get(sku)
                if not product and any_products:
                    product = any_products[len(line_defs) % len(any_products)]
                if not product:
                    print(f"Skip {spec['order_number']}: no products seeded yet")
                    line_defs = []
                    break
                line_defs.append((product, qty))

            if not line_defs:
                continue

            subtotal = sum(Decimal(str(p.price)) * qty for p, qty in line_defs)
            shipping = Decimal("0") if subtotal > 75 else Decimal("8")
            tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
            total = subtotal + shipping + tax

            if existing:
                existing.status = spec["status"]
                existing.subtotal = subtotal
                existing.shipping_fee = shipping
                existing.tax = tax
                existing.total = total
                existing.address_id = address.id
                existing.items.clear()
                db.flush()
                order = existing
                print(f"Updated order {spec['order_number']}")
            else:
                order = Order(
                    order_number=spec["order_number"],
                    customer_id=customer.id,
                    address_id=address.id,
                    status=spec["status"],
                    subtotal=subtotal,
                    discount=Decimal("0"),
                    shipping_fee=shipping,
                    tax=tax,
                    total=total,
                    created_at=created_at,
                )
                db.add(order)
                db.flush()
                print(f"Created order {spec['order_number']}")

            for product, qty in line_defs:
                db.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        name_snapshot=product.name,
                        price_snapshot=product.price,
                        qty=qty,
                    )
                )

        db.commit()
        print("Order seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
