"""Apply scripts/prod_reset.sql for go-live data wipe.

Keeps storefront catalog, Tirupati warehouse + STORE-1, system settings,
and a single admin user (phone/password 7013332720).

Usage (from renown-api, with venv + .env):
    python -m scripts.run_prod_reset
    python -m scripts.run_prod_reset --yes
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text

from app.core.config import DATABASE_URL
from app.core.security import hash_password, verify_password

SQL_PATH = pathlib.Path(__file__).resolve().parent / "prod_reset.sql"
ADMIN_PHONE = "7013332720"
ADMIN_PASSWORD = "7013332720"
KEEP_STORE_ID = 13
KEEP_WAREHOUSE_ID = 9


def _statements(sql: str) -> list[str]:
    # Drop full-line comments, then split on semicolons.
    lines = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        lines.append(line)
    body = "\n".join(lines)
    parts = [p.strip() for p in re.split(r";\s*\n", body) if p.strip()]
    out: list[str] = []
    for p in parts:
        p = p.strip().rstrip(";").strip()
        if p:
            out.append(p)
    return out


def main() -> None:
    yes = "--yes" in sys.argv
    if not yes:
        print(
            "This will WIPE customers/orders/analytics/ops history and\n"
            "delete all users except admin 7013332720, and all stores/\n"
            "warehouses except Tirupati STORE-1 + warehouse main.\n"
            "Catalog/products/banners/settings are KEPT.\n"
        )
        ans = input("Type YES to continue: ").strip()
        if ans != "YES":
            print("Aborted.")
            sys.exit(1)

    sql = SQL_PATH.read_text()
    stmts = _statements(sql)
    engine = create_engine(DATABASE_URL)
    pwd_hash = hash_password(ADMIN_PASSWORD)

    with engine.begin() as conn:
        store = (
            conn.execute(
                text("SELECT id, name, city FROM stores WHERE id = :id"),
                {"id": KEEP_STORE_ID},
            )
            .mappings()
            .first()
        )
        wh = (
            conn.execute(
                text("SELECT id, name, city FROM warehouses WHERE id = :id"),
                {"id": KEEP_WAREHOUSE_ID},
            )
            .mappings()
            .first()
        )
        admin = (
            conn.execute(
                text("SELECT id, phone, role FROM users WHERE phone = :p"),
                {"p": ADMIN_PHONE},
            )
            .mappings()
            .first()
        )
        if not store or not wh:
            raise SystemExit(f"Missing keep targets: store={store} warehouse={wh}")
        if not admin:
            raise SystemExit(f"Admin phone {ADMIN_PHONE} not found. Aborting.")
        print(f"Keep store: {dict(store)}")
        print(f"Keep warehouse: {dict(wh)}")
        print(f"Keep admin: {dict(admin)}")

        for i, stmt in enumerate(stmts, 1):
            preview = " ".join(stmt.split())[:100]
            print(f"[{i}/{len(stmts)}] {preview}")
            conn.execute(text(stmt))

        updated = conn.execute(
            text(
                """
                UPDATE users
                SET password_hash = :h,
                    role = 'admin',
                    is_active = TRUE,
                    store_id = NULL,
                    warehouse_id = NULL,
                    updated_at = NOW()
                WHERE phone = :p
                """
            ),
            {"h": pwd_hash, "p": ADMIN_PHONE},
        ).rowcount
        if updated != 1:
            raise SystemExit(f"Expected 1 admin password update, got {updated}")

        row = conn.execute(
            text("SELECT password_hash FROM users WHERE phone = :p"),
            {"p": ADMIN_PHONE},
        ).first()
        assert row and verify_password(ADMIN_PASSWORD, row[0])

        checks = {
            "products": conn.execute(text("SELECT COUNT(*) FROM products")).scalar(),
            "brands": conn.execute(text("SELECT COUNT(*) FROM brands")).scalar(),
            "categories": conn.execute(text("SELECT COUNT(*) FROM categories")).scalar(),
            "customers": conn.execute(text("SELECT COUNT(*) FROM customers")).scalar(),
            "orders": conn.execute(text("SELECT COUNT(*) FROM orders")).scalar(),
            "users": conn.execute(text("SELECT COUNT(*) FROM users")).scalar(),
            "stores": conn.execute(text("SELECT COUNT(*) FROM stores")).scalar(),
            "warehouses": conn.execute(text("SELECT COUNT(*) FROM warehouses")).scalar(),
            "store_inventory": conn.execute(
                text("SELECT COUNT(*) FROM store_inventory")
            ).scalar(),
            "warehouse_inventory": conn.execute(
                text("SELECT COUNT(*) FROM warehouse_inventory")
            ).scalar(),
            "otp_codes": conn.execute(text("SELECT COUNT(*) FROM otp_codes")).scalar(),
            "web_analytics_events": conn.execute(
                text("SELECT COUNT(*) FROM web_analytics_events")
            ).scalar(),
            "system_settings": conn.execute(
                text("SELECT COUNT(*) FROM system_settings")
            ).scalar(),
        }
        print("Post-reset counts:", checks)
        phones = [
            r[0]
            for r in conn.execute(text("SELECT phone FROM users ORDER BY id")).all()
        ]
        print("Remaining users:", phones)
        loc = conn.execute(
            text(
                """
                SELECT s.id AS store_id, s.name AS store, s.city AS store_city,
                       w.id AS wh_id, w.name AS warehouse, w.city AS wh_city
                FROM stores s
                LEFT JOIN warehouses w ON w.id = s.warehouse_id
                """
            )
        ).mappings().all()
        print("Locations:", [dict(x) for x in loc])

        if checks["products"] == 0:
            raise SystemExit("ABORT: products were wiped")
        if checks["users"] != 1 or phones != [ADMIN_PHONE]:
            raise SystemExit("ABORT: admin user state unexpected")
        if checks["stores"] != 1 or checks["warehouses"] != 1:
            raise SystemExit("ABORT: store/warehouse keep failed")
        if checks["customers"] or checks["orders"] or checks["otp_codes"]:
            raise SystemExit("ABORT: transactional wipe incomplete")

    print("prod_reset complete. Admin login: 7013332720 / 7013332720")


if __name__ == "__main__":
    main()
