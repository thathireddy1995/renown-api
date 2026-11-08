"""Move every store's stock back to its source warehouse.

Stores now sell straight from warehouse stock (Shop and POS), so frames sent
to stores earlier go back to the warehouse. Each store's return is recorded
as one completed store → warehouse stock transfer.

Dry run by default; pass --apply to write. Uses app.database (USE_LOCAL_DB).

    PYTHONPATH=. venv/bin/python scripts/return_store_stock_to_warehouse.py
    PYTHONPATH=. venv/bin/python scripts/return_store_stock_to_warehouse.py --apply
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import select

from app.core.stock_requests import store_source_warehouse
from app.core.stock_transfers import apply_transfer_completion, persist_stock_transfer
from app.database import SessionLocal, engine
from app.schemas import ProductVariant, Store, StoreInventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the transfers")
    args = parser.parse_args()

    print(f"Database: {engine.url.host}/{engine.url.database}")
    db = SessionLocal()
    rows = db.scalars(
        select(StoreInventory)
        .where(StoreInventory.on_hand > 0)
        .order_by(StoreInventory.store_id, StoreInventory.variant_id)
    ).all()
    by_store: dict[int, list[StoreInventory]] = defaultdict(list)
    for row in rows:
        by_store[row.store_id].append(row)
    if not by_store:
        print("No store stock to return.")
        return

    for store_id, lines in by_store.items():
        store = db.get(Store, store_id)
        warehouse = store_source_warehouse(db, store) if store else None
        if not store or not warehouse:
            print(f"Store {store_id}: no source warehouse, skipped")
            continue
        print(f"\n{store.name} → {warehouse.name}")
        for row in lines:
            sku = (db.get(ProductVariant, row.variant_id) or ProductVariant(sku="?")).sku
            note = ""
            if int(row.on_hand) != int(row.on_floor or 0) + int(row.backroom or 0):
                note = f"  (floor {row.on_floor} + backroom {row.backroom} ≠ on hand)"
            if int(row.reserved or 0):
                note += f"  (store reserved {row.reserved})"
            print(f"  {sku:<28} {int(row.on_hand):>4}{note}")
        total = sum(int(r.on_hand) for r in lines)
        print(f"  {'total':<28} {total:>4}")

        if not args.apply:
            continue
        transfer = persist_stock_transfer(
            db,
            from_warehouse_id=None,
            from_store_id=store.id,
            to_warehouse_id=warehouse.id,
            to_store_id=None,
            items=[{"variant_id": r.variant_id, "qty": int(r.on_hand)} for r in lines],
            status="completed",
            requested_by="Stock return: stores sell from warehouse",
        )
        apply_transfer_completion(db, transfer)
        db.commit()
        print(f"  returned as {transfer.transfer_number}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to move the stock.")


if __name__ == "__main__":
    main()
