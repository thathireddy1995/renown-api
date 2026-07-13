"""Seed warehouse ops data from staff-renown warehouse page mocks.

Run after seed_locations + seed_products (+ seed_inventory optional):

    python -m scripts.seed_warehouse_ops

Safe to re-run — matched by supplier code / PO / GRN / pick / pack / DO numbers.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select

from app.database import SessionLocal
from app.schemas import (
    DispatchOrder,
    DispatchOrderItem,
    Grn,
    GrnItem,
    Pack,
    PickList,
    PickListItem,
    ProductVariant,
    PurchaseOrder,
    Store,
    Supplier,
    Warehouse,
)

SUPPLIERS = [
    ("SUP-01", "Luxottica India", "orders@luxottica.in", "Frames · Sunglasses", 10, 3),
    ("SUP-02", "Zeiss Vision Care", "supply@zeiss.in", "Lenses", 14, 2),
    ("SUP-03", "Bausch & Lomb", "orders@bausch.in", "Contact Lens", 7, 1),
    ("SUP-04", "Essilor India", "supply@essilor.in", "Lenses", 12, 1),
    ("SUP-05", "Titan Eye+", "vendor@titan.co.in", "Frames", 8, 0),
]

GRNS = [
    ("GRN-4412", "PO-9921", "SUP-01", "Done", 3, 12, 240),
    ("GRN-4411", "PO-9915", "SUP-02", "Done", 5, 4, 400),
    ("GRN-4410", "PO-9912", "SUP-03", "Processing", 28, 8, 320),
    ("GRN-4409", "PO-9911", "SUP-04", "Pending", 30, 6, 180),
    ("GRN-4408", "PO-9905", "SUP-05", "Done", 50, 10, 260),
]

PICKS = [
    ("PL-3311", "Wave 12 (AM)", "Suresh K.", "Done", 42, 42),
    ("PL-3312", "Wave 12 (AM)", "Ravi P.", "Processing", 36, 20),
    ("PL-3313", "Wave 13 (PM)", "Amit S.", "Pending", 58, 0),
    ("PL-3314", "Wave 13 (PM)", None, "Pending", 24, 0),
]

DISPATCHES = [
    ("DO-8821", "store_replen", "OptiHub · Koramangala", "Blue Dart", "BD48291", "In Transit", 68),
    ("DO-8820", "store_replen", "OptiHub · Indiranagar", "Delhivery", "DL77120", "Delivered", 42),
    ("DO-8819", "d2c", "Rohit Verma · Mumbai", "Shiprocket", "SR11834", "Processing", 1),
    ("DO-8818", "store_replen", "OptiHub · Andheri", "Blue Dart", "BD48280", "Pending", 112),
    ("DO-8817", "d2c", "Neha Iyer · Pune", "Shiprocket", "SR11829", "Delivered", 2),
]

PACKS = [
    ("PK-1201", "DO-8821", "Ganesh V.", 4, Decimal("6.2"), "Done"),
    ("PK-1202", "DO-8820", "Ganesh V.", 2, Decimal("3.4"), "Done"),
    ("PK-1203", "DO-8819", "Sneha R.", 1, Decimal("0.4"), "Processing"),
    ("PK-1204", "DO-8818", None, 0, None, "Pending"),
]


def seed() -> None:
    db = SessionLocal()
    try:
        warehouse = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
        if not warehouse:
            print("No warehouse — run seed_locations first")
            return

        variants = list(
            db.scalars(select(ProductVariant).order_by(ProductVariant.id).limit(20)).all()
        )
        if not variants:
            print("No variants — run seed_products first")
            return

        stores = list(db.scalars(select(Store).order_by(Store.id)).all())
        supplier_by_code: dict[str, Supplier] = {}

        for code, name, contact, category, lead, open_hint in SUPPLIERS:
            row = db.scalar(select(Supplier).where(Supplier.code == code))
            if row:
                row.name = name
                row.contact = contact
                row.category = category
                row.lead_time_days = lead
                row.status = "Active"
            else:
                row = Supplier(
                    code=code,
                    name=name,
                    contact=contact,
                    category=category,
                    lead_time_days=lead,
                    status="Active",
                )
                db.add(row)
                db.flush()
            supplier_by_code[code] = row

            open_count = (
                db.scalar(
                    select(func.count()).where(
                        PurchaseOrder.supplier_id == row.id,
                        PurchaseOrder.status.in_(("Open", "Pending", "Processing")),
                    )
                )
                or 0
            )
            for i in range(max(0, open_hint - open_count)):
                db.add(
                    PurchaseOrder(
                        po_number=f"PO-OPEN-{code}-{i + 1}",
                        supplier_id=row.id,
                        status="Open",
                    )
                )

        db.flush()

        for grn_number, po_number, sup_code, status, hours_ago, sku_n, qty in GRNS:
            supplier = supplier_by_code[sup_code]
            po = db.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
            if not po:
                po = PurchaseOrder(
                    po_number=po_number,
                    supplier_id=supplier.id,
                    status="Received" if status == "Done" else "Open",
                )
                db.add(po)
                db.flush()
            else:
                po.supplier_id = supplier.id
                if status == "Done":
                    po.status = "Received"

            when = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
            grn = db.scalar(select(Grn).where(Grn.grn_number == grn_number))
            if grn:
                grn.purchase_order_id = po.id
                grn.warehouse_id = warehouse.id
                grn.status = status
                grn.received_at = when if status != "Pending" else None
                grn.items.clear()
                db.flush()
            else:
                grn = Grn(
                    grn_number=grn_number,
                    purchase_order_id=po.id,
                    warehouse_id=warehouse.id,
                    status=status,
                    received_at=when if status != "Pending" else None,
                    created_at=when,
                )
                db.add(grn)
                db.flush()

            n = min(sku_n, len(variants))
            per = max(1, qty // max(1, n))
            rem = qty
            for i in range(n):
                q = per if i < n - 1 else rem
                rem -= q
                db.add(
                    GrnItem(
                        grn_id=grn.id,
                        variant_id=variants[i % len(variants)].id,
                        qty_ordered=q,
                        qty_received=q if status != "Pending" else 0,
                    )
                )

        for list_number, wave, picker, status, total_qty, picked in PICKS:
            pl = db.scalar(select(PickList).where(PickList.list_number == list_number))
            if pl:
                pl.wave_number = wave
                pl.picker_name = picker
                pl.status = status
                pl.warehouse_id = warehouse.id
                pl.items.clear()
                db.flush()
            else:
                pl = PickList(
                    list_number=list_number,
                    wave_number=wave,
                    warehouse_id=warehouse.id,
                    picker_name=picker,
                    status=status,
                )
                db.add(pl)
                db.flush()

            db.add(
                PickListItem(
                    pick_list_id=pl.id,
                    variant_id=variants[0].id,
                    qty=total_qty,
                    picked_qty=picked,
                )
            )

        do_by_number: dict[str, DispatchOrder] = {}
        for do_number, dest_type, label, carrier, awb, status, items_qty in DISPATCHES:
            dest_id = stores[0].id if stores and dest_type == "store_replen" else None
            do = db.scalar(select(DispatchOrder).where(DispatchOrder.do_number == do_number))
            if do:
                do.warehouse_id = warehouse.id
                do.destination_type = dest_type
                do.destination_id = dest_id
                do.destination_label = label
                do.carrier = carrier
                do.awb = awb
                do.status = status
                do.items.clear()
                db.flush()
            else:
                do = DispatchOrder(
                    do_number=do_number,
                    warehouse_id=warehouse.id,
                    destination_type=dest_type,
                    destination_id=dest_id,
                    destination_label=label,
                    carrier=carrier,
                    awb=awb,
                    status=status,
                )
                db.add(do)
                db.flush()
            db.add(
                DispatchOrderItem(
                    dispatch_order_id=do.id,
                    variant_id=variants[0].id,
                    qty=items_qty,
                )
            )
            do_by_number[do_number] = do

        for pack_number, do_number, packer, boxes, weight, status in PACKS:
            do = do_by_number.get(do_number) or db.scalar(
                select(DispatchOrder).where(DispatchOrder.do_number == do_number)
            )
            pack = db.scalar(select(Pack).where(Pack.pack_number == pack_number))
            if pack:
                pack.dispatch_order_id = do.id if do else None
                pack.packer_name = packer
                pack.boxes = boxes
                pack.weight = weight
                pack.status = status
            else:
                db.add(
                    Pack(
                        pack_number=pack_number,
                        dispatch_order_id=do.id if do else None,
                        packer_name=packer,
                        boxes=boxes,
                        weight=weight,
                        status=status,
                    )
                )

        db.commit()
        print("Warehouse ops seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
