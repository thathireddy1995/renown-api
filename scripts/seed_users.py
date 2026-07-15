"""Seed the users table with one demo login per role.

Run locally after applying migrations:

    python -m scripts.seed_users

Safe to re-run — existing users are updated in place (matched by email).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.security import hash_password
from app.database import SessionLocal
from app.schemas import Store, User, Warehouse

SEED_USERS = [
    {
        "name": "Admin User",
        "email": "admin@renowneyewear.com",
        "phone": "9876543210",
        "password": "admin123",
        "role": "admin",
    },
    {
        "name": "Seed Admin",
        "email": "seed.admin@renowneyewear.com",
        "phone": "7013332720",
        "password": "7013332720",
        "role": "admin",
    },
    {
        "name": "Aarav Singh",
        "email": "store.manager@optihub.com",
        "phone": "9876543211",
        "password": "demo1234",
        "role": "store_manager",
        "link_first_store": True,
    },
    {
        "name": "Priya Kapoor",
        "email": "warehouse.manager@optihub.com",
        "phone": "9876543212",
        "password": "demo1234",
        "role": "warehouse_manager",
        "link_first_warehouse": True,
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        first_wh = db.scalar(select(Warehouse).order_by(Warehouse.id).limit(1))
        first_store = db.scalar(select(Store).order_by(Store.id).limit(1))

        if first_store and first_wh and first_store.warehouse_id is None:
            first_store.warehouse_id = first_wh.id

        for seed_user in SEED_USERS:
            existing = db.scalar(
                select(User).where(
                    (User.email == seed_user["email"]) | (User.phone == seed_user["phone"])
                )
            )
            password_hash = hash_password(seed_user["password"])
            warehouse_id = None
            store_id = None
            if seed_user.get("link_first_warehouse") and first_wh:
                warehouse_id = first_wh.id
            if seed_user.get("link_first_store") and first_store:
                store_id = first_store.id
                if first_store.warehouse_id:
                    warehouse_id = first_store.warehouse_id

            if existing:
                existing.name = seed_user["name"]
                existing.email = seed_user["email"]
                existing.phone = seed_user["phone"]
                existing.password_hash = password_hash
                existing.role = seed_user["role"]
                existing.is_active = True
                if warehouse_id is not None:
                    existing.warehouse_id = warehouse_id
                if store_id is not None:
                    existing.store_id = store_id
                print(f"Updated: {seed_user['phone']} / {seed_user['email']} ({seed_user['role']})")
            else:
                db.add(
                    User(
                        name=seed_user["name"],
                        email=seed_user["email"],
                        phone=seed_user["phone"],
                        password_hash=password_hash,
                        role=seed_user["role"],
                        warehouse_id=warehouse_id,
                        store_id=store_id,
                        is_active=True,
                    )
                )
                print(f"Created: {seed_user['phone']} / {seed_user['email']} ({seed_user['role']})")

        if first_wh:
            print(f"Warehouse manager linked to: {first_wh.code} · {first_wh.name}")
        if first_store:
            print(
                f"Store manager linked to: {first_store.code} · {first_store.name}"
                f" (warehouse_id={first_store.warehouse_id})"
            )
        else:
            print("No store found — store manager not linked yet")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
