"""Seed inventory audits from staff warehouse Audits.tsx mocks.

Run after seed_locations + seed_products (+ seed_inventory recommended):

    python -m scripts.seed_audits

Safe to re-run — matched by audit_number.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.database import SessionLocal
from app.schemas import (
    ImportJob,
    InventoryAudit,
    InventoryAuditItem,
    ProductVariant,
    Warehouse,
    WarehouseInventory,
)

# audit_number, zone, counted, expected, variance, auditor, days_ago, status
AUDITS = [
    ("AU-701", "A · Frames", 4820, 4830, -10, "Amit S.", 0, "completed"),
    ("AU-702", "B · Sunglasses", 2140, 2140, 0, "Ravi P.", 0, "completed"),
    ("AU-703", "C · Contact Lens", 3300, 3280, 20, "Sneha R.", 1, "completed"),
    ("AU-704", "D · Lens Blanks", 0, 5200, 0, None, None, "scheduled"),
]

IMPORT_JOBS = [
    (1042, "products", "frames-summer-2026.csv", "completed", 248, 0, "Aria Chen", 15),
    (1041, "products", "northline-update.xlsx", "completed", 92, 0, "Daniel Okafor", 16),
    (1040, "inventory", "stock-reconcile.csv", "completed", 1840, 0, "System", 17),
    (1039, "products", "atelier-readers.csv", "failed", 34, 34, "Mira Sato", 18),
    (1038, "products", "price-update-Q2.xlsx", "completed", 412, 0, "Aria Chen", 19),
]


def seed() -> None:
    db = SessionLocal()
    try:
        wh = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
        if not wh:
            print("No warehouses — run seed_locations first")
            return
        variants = list(
            db.scalars(select(ProductVariant).order_by(ProductVariant.id).limit(10)).all()
        )
        if not variants:
            print("No variants — run seed_products first")
            return

        now = datetime.now(timezone.utc)
        for num, zone, counted, expected, variance, auditor, days_ago, status in AUDITS:
            row = db.scalar(
                select(InventoryAudit).where(InventoryAudit.audit_number == num)
            )
            completed = None
            if status == "completed":
                completed = now - timedelta(days=days_ago or 0)
            if row:
                row.warehouse_id = wh.id
                row.zone = zone
                row.status = status
                row.auditor_name = auditor
                row.completed_at = completed
                print(f"Updated {num}")
            else:
                row = InventoryAudit(
                    audit_number=num,
                    warehouse_id=wh.id,
                    zone=zone,
                    status=status,
                    auditor_name=auditor,
                    completed_at=completed,
                )
                db.add(row)
                db.flush()
                print(f"Created {num}")

            # Replace items with a single aggregate-style line matching UI totals
            existing = list(
                db.scalars(
                    select(InventoryAuditItem).where(
                        InventoryAuditItem.inventory_audit_id == row.id
                    )
                ).all()
            )
            for item in existing:
                db.delete(item)
            db.flush()

            # Distribute expected across up to 3 variants, final variance on first
            v0 = variants[0]
            inv = db.scalar(
                select(WarehouseInventory).where(
                    WarehouseInventory.warehouse_id == wh.id,
                    WarehouseInventory.variant_id == v0.id,
                )
            )
            exp = expected if expected else (inv.on_hand if inv else 0)
            cnt = counted if status == "completed" else 0
            db.add(
                InventoryAuditItem(
                    inventory_audit_id=row.id,
                    variant_id=v0.id,
                    expected_qty=exp,
                    counted_qty=cnt,
                    variance=cnt - exp if status == "completed" else 0,
                )
            )

        db.commit()

        for job_id, job_type, file_name, status, rows, errors, by, hours_ago in IMPORT_JOBS:
            existing = db.get(ImportJob, job_id)
            created = now - timedelta(hours=hours_ago)
            if existing:
                existing.job_type = job_type
                existing.file_name = file_name
                existing.status = status
                existing.row_count = rows
                existing.error_count = errors
                existing.created_by = by
                existing.created_at = created
                existing.completed_at = created if status != "pending" else None
                print(f"Updated import job im-{job_id}")
            else:
                db.add(
                    ImportJob(
                        id=job_id,
                        job_type=job_type,
                        file_name=file_name,
                        status=status,
                        row_count=rows,
                        error_count=errors,
                        created_by=by,
                        created_at=created,
                        completed_at=created if status != "pending" else None,
                    )
                )
                print(f"Created import job im-{job_id}")
        db.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('import_jobs', 'id'), "
                "COALESCE((SELECT MAX(id) FROM import_jobs), 1))"
            )
        )
        db.commit()
        print("Audits seed complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
