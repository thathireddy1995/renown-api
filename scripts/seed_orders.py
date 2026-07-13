"""Seed two demo orders (RO-83291 delivered, RO-83402 shipped).

Run after migrations 0016–0018 and product/customer seeds:

    python -m scripts.seed_orders
    python -m scripts.seed_orders --bulk

Safe to re-run — matched by order_number.
"""

from __future__ import annotations

import argparse
import secrets
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

BULK_STATUSES = ["placed", "verified", "packed", "shipped", "delivered", "cancelled"]


def _ensure_order(
    db,
    *,
    customer: Customer,
    address: Address | None,
    products_by_sku: dict,
    any_products: list,
    order_number: str,
    status: str,
    days_ago: int,
    item_specs: list[tuple[str, int]],
) -> None:
    existing = db.scalar(
        select(Order)
        .where(Order.order_number == order_number)
        .options(selectinload(Order.items))
    )
    created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

    line_defs = []
    for sku, qty in item_specs:
        product = products_by_sku.get(sku)
        if not product and any_products:
            product = any_products[len(line_defs) % len(any_products)]
        if not product:
            print(f"Skip {order_number}: no products seeded yet")
            return
        line_defs.append((product, qty))

    if not line_defs:
        return

    subtotal = sum(Decimal(str(p.price)) * qty for p, qty in line_defs)
    shipping = Decimal("0") if subtotal > 75 else Decimal("8")
    tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.01"))
    total = subtotal + shipping + tax

    if existing:
        existing.status = status
        existing.subtotal = subtotal
        existing.shipping_fee = shipping
        existing.tax = tax
        existing.total = total
        existing.address_id = address.id if address else None
        existing.items.clear()
        db.flush()
        order = existing
        print(f"Updated order {order_number}")
    else:
        order = Order(
            order_number=order_number,
            customer_id=customer.id,
            address_id=address.id if address else None,
            status=status,
            subtotal=subtotal,
            discount=Decimal("0"),
            shipping_fee=shipping,
            tax=tax,
            total=total,
            created_at=created_at,
        )
        db.add(order)
        db.flush()
        print(f"Created order {order_number}")

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


def seed(bulk: bool = False, bulk_count: int = 40) -> None:
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

        products_by_sku = {p.sku: p for p in db.scalars(select(Product)).all()}
        any_products = list(products_by_sku.values())

        for spec in ORDERS:
            _ensure_order(
                db,
                customer=customer,
                address=address,
                products_by_sku=products_by_sku,
                any_products=any_products,
                order_number=spec["order_number"],
                status=spec["status"],
                days_ago=spec["days_ago"],
                item_specs=spec["items"],
            )

        if bulk:
            # Extra customers + orders for admin pagination demos.
            for i in range(1, 6):
                phone = f"90000000{10 + i}"
                extra = db.scalar(select(Customer).where(Customer.phone == phone))
                if not extra:
                    extra = Customer(
                        name=f"Bulk Customer {i}",
                        phone=phone,
                        email=f"bulk{i}@renowneyewear.com",
                        is_active=True,
                    )
                    db.add(extra)
                    db.flush()
                    print(f"Created bulk customer {phone}")

                for j in range(bulk_count // 5):
                    num = f"RO-B{i}{j:03d}"
                    status = BULK_STATUSES[(i + j) % len(BULK_STATUSES)]
                    sku = (
                        any_products[(i + j) % len(any_products)].sku
                        if any_products
                        else "RO-1000"
                    )
                    _ensure_order(
                        db,
                        customer=extra,
                        address=None,
                        products_by_sku=products_by_sku,
                        any_products=any_products,
                        order_number=num,
                        status=status,
                        days_ago=1 + (i * 3 + j) % 60,
                        item_specs=[(sku, 1 + (j % 2))],
                    )

            # Fill remaining volume on demo customer if needed
            existing_bulk = {
                o.order_number
                for o in db.scalars(
                    select(Order).where(Order.order_number.like("RO-9%"))
                ).all()
            }
            made = 0
            while made < max(0, bulk_count - 25):
                num = f"RO-9{secrets.randbelow(90_000) + 10_000}"
                if num in existing_bulk:
                    continue
                existing_bulk.add(num)
                status = BULK_STATUSES[made % len(BULK_STATUSES)]
                sku = (
                    any_products[made % len(any_products)].sku
                    if any_products
                    else "RO-1000"
                )
                _ensure_order(
                    db,
                    customer=customer,
                    address=address,
                    products_by_sku=products_by_sku,
                    any_products=any_products,
                    order_number=num,
                    status=status,
                    days_ago=1 + (made % 45),
                    item_specs=[(sku, 1)],
                )
                made += 1

        db.commit()
        print("Order seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo orders")
    parser.add_argument(
        "--bulk",
        action="store_true",
        help="Create extra customers/orders for admin pagination testing",
    )
    parser.add_argument("--count", type=int, default=40, help="Approx bulk order count")
    args = parser.parse_args()
    seed(bulk=args.bulk, bulk_count=args.count)
