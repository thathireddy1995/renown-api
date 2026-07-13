"""Seed warehouse/store inventory from admin mocks, matched by variant SKU.

Run after seed_locations + seed_products:

    python -m scripts.seed_inventory

Safe to re-run — matched by (warehouse/store, variant).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import SessionLocal
from app.schemas import ProductVariant, Store, StoreInventory, Warehouse, WarehouseInventory

# Mock SKUs that differ slightly from Phase 2 seed variants.
SKU_ALIASES = {
    "QUL-RDR-TOR-50": "QUI-RDR-BLK-50",
    "PVD-CTL-030-DAY": "PVD-DAY-CLR-00",
    "CRS-CTL-M-050": "CRS-MTH-CLR-00",
    "ATL-BRW-BLK-52": "ATL-BRW-GUN-54",
    "SRN-OVL-CLR-50": "SOR-OVL-OLV-52",
    "VRS-RDR-BLK-52": "VRS-RDR-TOR-50",
}

WH_INV = [
    # sku, bin, on_hand, reserved, reorder
    ("HAL-RND-TOR-50", "A-12-03", 142, 18, 40),
    ("HAL-RND-BLK-50", "A-12-04", 88, 22, 40),
    ("MAR-AVI-GLD-54", "B-04-11", 36, 8, 30),
    ("MAR-AVI-GUN-54", "B-04-12", 22, 4, 30),
    ("LIN-SQR-BLK-52", "C-08-02", 210, 14, 50),
    ("LIN-SQR-NAV-52", "C-08-03", 12, 6, 30),
    ("STW-CAT-TOR-50", "D-01-09", 74, 12, 40),
    ("STW-CAT-BRG-50", "D-01-10", 8, 3, 20),
    ("BCN-WIR-GLD-48", "A-14-05", 320, 20, 60),
    ("RDG-POL-BLK-54", "E-02-01", 156, 30, 50),
    ("QUL-RDR-TOR-50", "F-06-14", 4, 0, 25),
    ("PVD-CTL-030-DAY", "G-11-02", 1240, 60, 400),
    ("ATL-BRW-BLK-52", "A-15-01", 68, 9, 40),
    ("SRN-OVL-CLR-50", "B-06-07", 48, 5, 30),
    ("VRS-RDR-BLK-52", "F-07-02", 92, 4, 40),
    ("CRS-CTL-M-050", "G-12-01", 620, 40, 200),
]

STORE_INV = [
    # sku, on_floor, backroom, reserved, reorder
    ("HAL-RND-TOR-50", 8, 12, 2, 6),
    ("HAL-RND-BLK-50", 4, 6, 1, 6),
    ("MAR-AVI-GLD-54", 2, 4, 0, 5),
    ("LIN-SQR-BLK-52", 12, 20, 3, 8),
    ("STW-CAT-TOR-50", 5, 3, 1, 6),
    ("BCN-WIR-GLD-48", 14, 22, 2, 10),
    ("RDG-POL-BLK-54", 9, 11, 4, 8),
    ("QUL-RDR-TOR-50", 1, 0, 0, 5),
    ("ATL-BRW-BLK-52", 6, 4, 1, 5),
    ("SRN-OVL-CLR-50", 3, 2, 0, 5),
]


def _resolve_variant(by_sku: dict[str, ProductVariant], sku: str) -> ProductVariant | None:
    return by_sku.get(sku) or by_sku.get(SKU_ALIASES.get(sku, ""))


def seed() -> None:
    db = SessionLocal()
    try:
        warehouses = list(db.scalars(select(Warehouse).order_by(Warehouse.id)).all())
        stores = list(db.scalars(select(Store).order_by(Store.id)).all())
        if not warehouses:
            print("No warehouses — run seed_locations first")
            return
        if not stores:
            print("No stores — run seed_locations first")
            return

        by_sku = {v.sku: v for v in db.scalars(select(ProductVariant)).all()}
        if not by_sku:
            print("No variants — run seed_products first")
            return

        for i, (sku, bin_loc, on_hand, reserved, reorder) in enumerate(WH_INV):
            variant = _resolve_variant(by_sku, sku)
            if not variant:
                print(f"Skip WH inv {sku}: variant not found")
                continue
            wh = warehouses[i % len(warehouses)]
            row = db.scalar(
                select(WarehouseInventory).where(
                    WarehouseInventory.warehouse_id == wh.id,
                    WarehouseInventory.variant_id == variant.id,
                )
            )
            if row:
                row.bin_location = bin_loc
                row.on_hand = on_hand
                row.reserved = reserved
                row.reorder_point = reorder
                print(f"Updated WH inv {wh.code} {variant.sku}")
            else:
                db.add(
                    WarehouseInventory(
                        warehouse_id=wh.id,
                        variant_id=variant.id,
                        bin_location=bin_loc,
                        on_hand=on_hand,
                        reserved=reserved,
                        reorder_point=reorder,
                    )
                )
                print(f"Created WH inv {wh.code} {variant.sku}")

        store_slice = stores[:4]
        for sku, on_floor, backroom, reserved, reorder in STORE_INV:
            variant = _resolve_variant(by_sku, sku)
            if not variant:
                print(f"Skip store inv {sku}: variant not found")
                continue
            for j, store in enumerate(store_slice):
                factor = 1 - j * 0.15
                floor = max(0, round(on_floor * factor))
                back = max(0, round(backroom * factor))
                row = db.scalar(
                    select(StoreInventory).where(
                        StoreInventory.store_id == store.id,
                        StoreInventory.variant_id == variant.id,
                    )
                )
                if row:
                    row.on_floor = floor
                    row.backroom = back
                    row.on_hand = floor + back
                    row.reserved = reserved
                    row.reorder_point = reorder
                    print(f"Updated store inv {store.code} {variant.sku}")
                else:
                    db.add(
                        StoreInventory(
                            store_id=store.id,
                            variant_id=variant.id,
                            on_floor=floor,
                            backroom=back,
                            on_hand=floor + back,
                            reserved=reserved,
                            reorder_point=reorder,
                        )
                    )
                    print(f"Created store inv {store.code} {variant.sku}")

        db.commit()
        print("Inventory seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
