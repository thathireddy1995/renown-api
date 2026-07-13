"""Seed employees from admin Employees page and staff store Staff.tsx.

Run after seed_locations:

    python -m scripts.seed_employees

Safe to re-run — matched by employee_code.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import SessionLocal
from app.schemas import Employee, Store, Warehouse

# Admin employees mock (admin.employees.tsx)
ADMIN_STORE = [
    ("SE-201", "Aria Chen", "Store Manager", "Bengaluru · Indiranagar", "Day", "active", None, 0),
    ("SE-202", "Rohan Bhatt", "Optician", "Bengaluru · Indiranagar", "Day", "active", None, 0),
    ("SE-203", "Sanya Kapoor", "Sales Associate", "Bengaluru · Indiranagar", "Evening", "active", None, 0),
    ("SE-204", "Kavya Rao", "Store Manager", "Bengaluru · UB City", "Day", "active", None, 0),
    ("SE-205", "Daniel Okafor", "Store Manager", "Mumbai · Bandra", "Day", "active", None, 0),
    ("SE-206", "Nisha Verma", "Optometrist", "Mumbai · Bandra", "Day", "active", None, 0),
    ("SE-207", "Mira Sato", "Store Manager", "Delhi · Khan Market", "Day", "active", None, 0),
    ("SE-208", "Ishan Patel", "Sales Associate", "Delhi · Khan Market", "Evening", "inactive", None, 0),
    ("SE-209", "Kian Park", "Store Manager", "Singapore · Orchard", "Day", "active", None, 0),
    ("SE-210", "Hana Rossi", "Store Manager", "Dubai · Mall of Emirates", "Day", "inactive", None, 0),
]

ADMIN_WH = [
    ("E-101", "Priya Menon", "Warehouse Manager", "Bengaluru Central", "Day", "active", None, 0),
    ("E-102", "Reza Nazari", "Senior Picker", "Bengaluru Central", "Day", "active", None, 0),
    ("E-103", "Tomás Vega", "Picker", "Bengaluru Central", "Day", "active", None, 0),
    ("E-104", "Lina Okonkwo", "Packer", "Bengaluru Central", "Day", "active", None, 0),
    ("E-105", "Arjun Desai", "Warehouse Manager", "Mumbai West", "Day", "active", None, 0),
    ("E-106", "Iona Lambert", "Picker", "Mumbai West", "Day", "active", None, 0),
    ("E-107", "Sofia Bianchi", "Warehouse Manager", "Dubai Logistics", "Day", "inactive", None, 0),
    ("E-108", "Noah Kim", "Picker", "Singapore Hub", "Night", "active", None, 0),
    ("E-109", "Noor Patel", "Receiver", "Delhi NCR", "Day", "active", None, 0),
    ("E-110", "Ravi Sharma", "Forklift Operator", "Delhi NCR", "Night", "active", None, 0),
]

# Staff store Staff.tsx — unique codes ST-* to avoid clash with admin warehouse E-*
STAFF_STORE = [
    ("ST-101", "Rakesh Menon", "Optician", "+91 98123 00001", "10:00 – 19:00", "active", 184200),
    ("ST-102", "Ananya Bose", "Sales Executive", "+91 98123 00002", "10:00 – 19:00", "active", 122000),
    ("ST-103", "Priya Kaur", "Sales Executive", "+91 98123 00003", "12:00 – 21:00", "active", 96500),
    ("ST-104", "Rohan Sen", "Trainee", "+91 98123 00004", "12:00 – 21:00", "active", 78300),
    ("ST-105", "Dr. Kapoor", "Optometrist", "+91 98123 00005", "11:00 – 18:00", "active", 0),
]


def _upsert(
    db,
    *,
    code: str,
    name: str,
    role: str,
    shift: str,
    status: str,
    store_id: int | None,
    warehouse_id: int | None,
    phone: str | None,
    mtd: Decimal,
) -> None:
    row = db.scalar(select(Employee).where(Employee.employee_code == code))
    if row:
        row.name = name
        row.job_role = role[:40]
        row.shift = shift[:20]
        row.status = status
        row.store_id = store_id
        row.warehouse_id = warehouse_id
        row.phone = phone
        row.mtd_sales = mtd
        print(f"Updated {code}")
    else:
        db.add(
            Employee(
                employee_code=code,
                name=name,
                job_role=role[:40],
                shift=shift[:20],
                status=status,
                store_id=store_id,
                warehouse_id=warehouse_id,
                phone=phone,
                mtd_sales=mtd,
            )
        )
        print(f"Created {code}")


def seed() -> None:
    db = SessionLocal()
    try:
        stores = {s.name: s for s in db.scalars(select(Store)).all()}
        warehouses = {w.name: w for w in db.scalars(select(Warehouse)).all()}
        if not stores and not warehouses:
            print("No locations — run seed_locations first")
            return

        default_store = db.scalar(
            select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
        ) or next(iter(stores.values()), None)

        for code, name, role, loc, shift, status, phone, mtd in ADMIN_STORE:
            store = stores.get(loc) or default_store
            _upsert(
                db,
                code=code,
                name=name,
                role=role,
                shift=shift,
                status=status,
                store_id=store.id if store else None,
                warehouse_id=None,
                phone=phone,
                mtd=Decimal(mtd),
            )

        for code, name, role, loc, shift, status, phone, mtd in ADMIN_WH:
            wh = warehouses.get(loc)
            _upsert(
                db,
                code=code,
                name=name,
                role=role,
                shift=shift,
                status=status,
                store_id=None,
                warehouse_id=wh.id if wh else None,
                phone=phone,
                mtd=Decimal(mtd),
            )

        for code, name, role, phone, shift, status, mtd in STAFF_STORE:
            _upsert(
                db,
                code=code,
                name=name,
                role=role,
                shift=shift,
                status=status,
                store_id=default_store.id if default_store else None,
                warehouse_id=None,
                phone=phone,
                mtd=Decimal(mtd),
            )

        db.commit()
        print("Employees seed complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
