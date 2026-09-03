"""Seed warehouses and retail stores from admin mock lists.

Run after migrations 0020–0021:

    python -m scripts.seed_locations

Safe to re-run — matched by code.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import SessionLocal
from app.schemas import Store, Warehouse

WAREHOUSES = [
    {
        "code": "WH-BLR",
        "name": "Bengaluru Central",
        "city": "Bengaluru",
        "country": "India",
        "manager": "Aria Chen",
        "capacity": 24000,
        "staff": 42,
        "status": "Active",
        "address": "Whitefield Logistics Park, Bengaluru",
    },
    {
        "code": "WH-MUM",
        "name": "Mumbai West",
        "city": "Mumbai",
        "country": "India",
        "manager": "Daniel Okafor",
        "capacity": 18000,
        "staff": 34,
        "status": "Active",
        "address": "Andheri logistics belt, Mumbai",
    },
    {
        "code": "WH-DEL",
        "name": "Delhi NCR",
        "city": "Gurugram",
        "country": "India",
        "manager": "Mira Sato",
        "capacity": 22000,
        "staff": 28,
        "status": "Active",
        "address": "Udyog Vihar, Gurugram",
    },
    {
        "code": "WH-DXB",
        "name": "Dubai Logistics",
        "city": "Dubai",
        "country": "UAE",
        "manager": "Hana Rossi",
        "capacity": 12000,
        "staff": 18,
        "status": "Maintenance",
        "address": "Jebel Ali Free Zone, Dubai",
    },
    {
        "code": "WH-SIN",
        "name": "Singapore Hub",
        "city": "Singapore",
        "country": "SG",
        "manager": "Kian Park",
        "capacity": 15000,
        "staff": 22,
        "status": "Active",
        "address": "Tuas Link, Singapore",
    },
    {
        "code": "WH-HYD",
        "name": "Hyderabad Hub",
        "city": "Hyderabad",
        "country": "India",
        "manager": "Priya Sharma",
        "capacity": 16000,
        "staff": 20,
        "status": "Active",
        "address": "Gachibowli logistics park, Hyderabad",
    },
]

STORES = [
    {
        "code": "ST-BLR-01",
        "name": "Bengaluru · Indiranagar",
        "city": "Bengaluru",
        "country": "India",
        "address": "12th Main, Indiranagar",
        "manager": "Aria Chen",
        "phone": "+91 80 4110 2233",
        "hours": "10:00 – 21:00",
        "staff": 12,
        "status": "Open",
        "today_revenue": Decimal("184200"),
        "today_orders": 42,
    },
    {
        "code": "ST-BLR-02",
        "name": "Bengaluru · UB City",
        "city": "Bengaluru",
        "country": "India",
        "address": "Vittal Mallya Road",
        "manager": "Kavya Rao",
        "phone": "+91 80 4110 2244",
        "hours": "11:00 – 22:00",
        "staff": 10,
        "status": "Open",
        "today_revenue": Decimal("221400"),
        "today_orders": 38,
    },
    {
        "code": "ST-MUM-01",
        "name": "Mumbai · Bandra",
        "city": "Mumbai",
        "country": "India",
        "address": "Linking Road, Bandra West",
        "manager": "Daniel Okafor",
        "phone": "+91 22 6110 8877",
        "hours": "10:00 – 21:30",
        "staff": 14,
        "status": "Open",
        "today_revenue": Decimal("268900"),
        "today_orders": 54,
    },
    {
        "code": "ST-DEL-01",
        "name": "Delhi · Khan Market",
        "city": "New Delhi",
        "country": "India",
        "address": "Khan Market Middle Lane",
        "manager": "Mira Sato",
        "phone": "+91 11 4110 5566",
        "hours": "10:00 – 20:30",
        "staff": 9,
        "status": "Open",
        "today_revenue": Decimal("152800"),
        "today_orders": 31,
    },
    {
        "code": "ST-DXB-01",
        "name": "Dubai · Mall of Emirates",
        "city": "Dubai",
        "country": "UAE",
        "address": "Sheikh Zayed Road",
        "manager": "Hana Rossi",
        "phone": "+971 4 380 1122",
        "hours": "10:00 – 23:00",
        "staff": 11,
        "status": "Maintenance",
        "today_revenue": Decimal("0"),
        "today_orders": 0,
    },
    {
        "code": "ST-SIN-01",
        "name": "Singapore · Orchard",
        "city": "Singapore",
        "country": "SG",
        "address": "Orchard Road, Wisma Atria",
        "manager": "Kian Park",
        "phone": "+65 6733 4210",
        "hours": "11:00 – 22:00",
        "staff": 8,
        "status": "Open",
        "today_revenue": Decimal("198450"),
        "today_orders": 29,
    },
    {
        "code": "ST-HYD-01",
        "name": "Hyderabad · Banjara Hills",
        "city": "Hyderabad",
        "country": "India",
        "address": "Road No. 12, Banjara Hills, Hyderabad 500034",
        "manager": "Priya Sharma",
        "phone": "+91 40 4000 1234",
        "hours": "10:00 – 21:00",
        "staff": 10,
        "status": "Open",
        "today_revenue": Decimal("0"),
        "today_orders": 0,
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        for spec in WAREHOUSES:
            row = db.scalar(select(Warehouse).where(Warehouse.code == spec["code"]))
            if row:
                for k, v in spec.items():
                    setattr(row, k, v)
                print(f"Updated warehouse {spec['code']}")
            else:
                db.add(Warehouse(**spec))
                print(f"Created warehouse {spec['code']}")

        for spec in STORES:
            row = db.scalar(select(Store).where(Store.code == spec["code"]))
            if row:
                for k, v in spec.items():
                    setattr(row, k, v)
                print(f"Updated store {spec['code']}")
            else:
                db.add(Store(**spec))
                print(f"Created store {spec['code']}")

        db.commit()

        code_to_wh = {
            w.code: w.id
            for w in db.scalars(select(Warehouse)).all()
        }
        store_wh = {
            "ST-BLR-01": "WH-BLR",
            "ST-BLR-02": "WH-BLR",
            "ST-MUM-01": "WH-MUM",
            "ST-DEL-01": "WH-DEL",
            "ST-DXB-01": "WH-DXB",
            "ST-SIN-01": "WH-SIN",
            "ST-HYD-01": "WH-HYD",
        }
        for store in db.scalars(select(Store)).all():
            wh_code = store_wh.get(store.code)
            if wh_code and code_to_wh.get(wh_code):
                store.warehouse_id = code_to_wh[wh_code]
        db.commit()
        print("Location seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
