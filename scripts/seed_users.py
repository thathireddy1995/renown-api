"""Seed the users table with one demo login per role.

Run locally after applying migrations/0001_create_users_table.sql:

    source venv/bin/activate
    python -m scripts.seed_users

Safe to re-run — existing users are updated in place (matched by email).
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.security import hash_password
from app.database import SessionLocal
from app.schemas import User

SEED_USERS = [
    {
        "name": "Admin User",
        "email": "admin@renowneyewear.com",
        "phone": "9876543210",
        "password": "admin123",
        "role": "admin",
    },
    {
        "name": "Aarav Singh",
        "email": "store.manager@optihub.com",
        "phone": "9876543211",
        "password": "demo1234",
        "role": "store_manager",
    },
    {
        "name": "Priya Kapoor",
        "email": "warehouse.manager@optihub.com",
        "phone": "9876543212",
        "password": "demo1234",
        "role": "warehouse_manager",
    },
]


def seed() -> None:
    db = SessionLocal()
    try:
        for seed_user in SEED_USERS:
            existing = db.scalar(select(User).where(User.email == seed_user["email"]))
            password_hash = hash_password(seed_user["password"])

            if existing:
                existing.name = seed_user["name"]
                existing.phone = seed_user["phone"]
                existing.password_hash = password_hash
                existing.role = seed_user["role"]
                existing.is_active = True
                print(f"Updated: {seed_user['email']} ({seed_user['role']})")
            else:
                db.add(
                    User(
                        name=seed_user["name"],
                        email=seed_user["email"],
                        phone=seed_user["phone"],
                        password_hash=password_hash,
                        role=seed_user["role"],
                        is_active=True,
                    )
                )
                print(f"Created: {seed_user['email']} ({seed_user['role']})")

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
