"""Seed stock transfers, transfer requests, and allocations.

Run after seed_locations + seed_products (+ seed_orders optional):

    python -m scripts.seed_transfers

Safe to re-run — matched by transfer/request/allocation numbers.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import SessionLocal
from app.schemas import (
    Order,
    ProductVariant,
    StockAllocation,
    StockTransfer,
    StockTransferItem,
    TransferRequest,
    Warehouse,
)

# transfer_number, from_code, to_code, sku, qty, status, eta_days, created_days
TRANSFERS = [
    ("TR-2201", "WH-BLR", "WH-MUM", "HAL-RND-TOR-50", 40, "in_transit", 2, 15),
    ("TR-2202", "WH-DEL", "WH-BLR", "LIN-SQR-NAV-52", 60, "completed", 0, 17),
    ("TR-2203", "WH-SIN", "WH-DXB", "MAR-AVI-GUN-54", 25, "requested", 5, 13),
    ("TR-2204", "WH-MUM", "WH-DEL", "BCN-WIR-GLD-48", 120, "picking", 3, 14),
    ("TR-2205", "WH-BLR", "WH-SIN", "RDG-POL-BLK-54", 30, "approved", 4, 13),
    ("TR-2206", "WH-DEL", "WH-MUM", "STW-CAT-BRG-50", 18, "rejected", None, 15),
    ("TR-2207", "WH-BLR", "WH-DEL", "ATL-BRW-GUN-54", 45, "packing", 3, 14),
    ("TR-2208", "WH-MUM", "WH-BLR", "PVD-DAY-CLR-00", 200, "received", 1, 16),
]

# request_number, requester, target, sku, qty, urgency, status, days_ago
REQUESTS = [
    ("TQ-8801", "WH-MUM", "WH-BLR", "HAL-RND-BLK-50", 30, "High", "pending", 13),
    ("TQ-8802", "WH-DEL", "WH-BLR", "STW-CAT-TOR-50", 20, "Medium", "approved", 14),
    ("TQ-8803", "WH-SIN", "WH-MUM", "PVD-DAY-CLR-00", 200, "Low", "pending", 13),
    ("TQ-8804", "WH-DXB", "WH-DEL", "MAR-AVI-GLD-54", 12, "High", "rejected", 15),
]

# allocation_number, order_number, sku, qty, wh_code, status, picker, hours_ago
ALLOCATIONS = [
    ("AL-4021", "ORD-88214", "HAL-RND-TOR-50", 2, "WH-BLR", "Allocated", "Reza N.", 8),
    ("AL-4022", "ORD-88215", "MAR-AVI-GLD-54", 1, "WH-MUM", "Picking", "Iona L.", 7),
    ("AL-4023", "ORD-88218", "LIN-SQR-BLK-52", 3, "WH-BLR", "Packed", "Tomás V.", 6),
    ("AL-4024", "ORD-88221", "RDG-POL-BLK-54", 1, "WH-DEL", "Allocated", "—", 5),
    ("AL-4025", "ORD-88223", "STW-CAT-TOR-50", 2, "WH-BLR", "Ready to ship", "Reza N.", 4),
    ("AL-4026", "ORD-88224", "BCN-WIR-GLD-48", 1, "WH-SIN", "Picking", "Kian P.", 3),
    ("AL-4027", "ORD-88225", "PVD-DAY-CLR-00", 6, "WH-MUM", "Backorder", "—", 2),
    ("AL-4028", "ORD-88227", "ATL-BRW-GUN-54", 1, "WH-DEL", "Allocated", "—", 1),
]

SKU_ALIASES = {
    "ATL-BRW-BLK-52": "ATL-BRW-GUN-54",
    "PVD-CTL-030-DAY": "PVD-DAY-CLR-00",
}


def _variant(by_sku: dict, sku: str) -> ProductVariant | None:
    return by_sku.get(sku) or by_sku.get(SKU_ALIASES.get(sku, ""))


def seed() -> None:
    db = SessionLocal()
    try:
        warehouses = {
            w.code: w for w in db.scalars(select(Warehouse)).all()
        }
        if not warehouses:
            print("No warehouses — run seed_locations first")
            return

        by_sku = {v.sku: v for v in db.scalars(select(ProductVariant)).all()}
        if not by_sku:
            print("No variants — run seed_products first")
            return

        orders = {o.order_number: o for o in db.scalars(select(Order)).all()}

        for num, fcode, tcode, sku, qty, status, eta_days, created_days in TRANSFERS:
            src = warehouses.get(fcode)
            dst = warehouses.get(tcode)
            variant = _variant(by_sku, sku)
            if not src or not dst or not variant:
                print(f"Skip transfer {num}: missing warehouse/variant")
                continue
            created = datetime.now(timezone.utc) - timedelta(days=created_days)
            eta = (
                date.today() + timedelta(days=eta_days)
                if eta_days is not None
                else None
            )
            row = db.scalar(
                select(StockTransfer).where(StockTransfer.transfer_number == num)
            )
            if row:
                row.from_warehouse_id = src.id
                row.to_warehouse_id = dst.id
                row.status = status
                row.eta = eta
                row.items.clear()
                db.flush()
            else:
                row = StockTransfer(
                    transfer_number=num,
                    from_warehouse_id=src.id,
                    to_warehouse_id=dst.id,
                    status=status,
                    eta=eta,
                    created_at=created,
                )
                db.add(row)
                db.flush()
            db.add(
                StockTransferItem(
                    stock_transfer_id=row.id, variant_id=variant.id, qty=qty
                )
            )
            print(f"Upserted transfer {num}")

        for num, req_code, tgt_code, sku, qty, urgency, status, days_ago in REQUESTS:
            req_wh = warehouses.get(req_code)
            tgt_wh = warehouses.get(tgt_code)
            variant = _variant(by_sku, sku)
            if not req_wh or not tgt_wh or not variant:
                print(f"Skip request {num}")
                continue
            created = datetime.now(timezone.utc) - timedelta(days=days_ago)
            row = db.scalar(
                select(TransferRequest).where(TransferRequest.request_number == num)
            )
            if row:
                row.requester_warehouse_id = req_wh.id
                row.target_warehouse_id = tgt_wh.id
                row.variant_id = variant.id
                row.qty_requested = qty
                row.urgency = urgency
                row.status = status
            else:
                db.add(
                    TransferRequest(
                        request_number=num,
                        requester_warehouse_id=req_wh.id,
                        target_warehouse_id=tgt_wh.id,
                        variant_id=variant.id,
                        qty_requested=qty,
                        urgency=urgency,
                        status=status,
                        created_at=created,
                    )
                )
            print(f"Upserted request {num}")

        for num, order_num, sku, qty, wh_code, status, picker, hours_ago in ALLOCATIONS:
            wh = warehouses.get(wh_code)
            variant = _variant(by_sku, sku)
            if not wh or not variant:
                print(f"Skip allocation {num}")
                continue
            order = orders.get(order_num)
            created = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
            row = db.scalar(
                select(StockAllocation).where(StockAllocation.allocation_number == num)
            )
            if row:
                row.order_id = order.id if order else None
                row.order_number = order_num
                row.variant_id = variant.id
                row.warehouse_id = wh.id
                row.qty = qty
                row.status = status
                row.picker_name = None if picker == "—" else picker
            else:
                db.add(
                    StockAllocation(
                        allocation_number=num,
                        order_id=order.id if order else None,
                        order_number=order_num,
                        variant_id=variant.id,
                        warehouse_id=wh.id,
                        qty=qty,
                        status=status,
                        picker_name=None if picker == "—" else picker,
                        created_at=created,
                    )
                )
            print(f"Upserted allocation {num}")

        db.commit()
        print("Transfer seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
