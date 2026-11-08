"""Warehouse stock reservation for placed orders.

Online and store sales all come straight from warehouse stock; stores hold
none of their own. Every online order (customer web or store-placed on
behalf) holds its frames at the warehouse so availability
(``on_hand - reserved``) reflects committed orders, and store counter (POS)
sales take unreserved warehouse stock immediately.

Single-warehouse model: we reserve against whichever warehouse rows stock each
variant. Reservation is best-effort and never blocks checkout — it reserves what
exists and logs a shortfall, rather than failing an order. Dispatch consumes the
reservation (``on_hand`` and ``reserved`` both drop); cancel releases it.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.schemas import WarehouseInventory

logger = logging.getLogger(__name__)

# A line is (variant_id, qty). variant_id may be None for un-mapped items.
Line = tuple[int | None, int]


def _rows_for_variant(db: Session, variant_id: int) -> list[WarehouseInventory]:
    return list(
        db.scalars(
            select(WarehouseInventory)
            .where(WarehouseInventory.variant_id == variant_id)
            .order_by(WarehouseInventory.id.asc())
            .with_for_update()
        ).all()
    )


def reserve_variant(db: Session, variant_id: int, qty: int) -> int:
    """Reserve up to ``qty`` across the variant's warehouse rows. Returns reserved."""
    if qty <= 0:
        return 0
    remaining = qty
    for row in _rows_for_variant(db, variant_id):
        if remaining <= 0:
            break
        available = int(row.on_hand or 0) - int(row.reserved or 0)
        if available <= 0:
            continue
        take = min(available, remaining)
        row.reserved = int(row.reserved or 0) + take
        remaining -= take
    if remaining > 0:
        logger.info(
            "Reservation short for variant %s: %s of %s left unreserved",
            variant_id,
            remaining,
            qty,
        )
    return qty - remaining


def release_variant(db: Session, variant_id: int, qty: int) -> None:
    """Free up to ``qty`` of reservation across the variant's warehouse rows."""
    if qty <= 0:
        return
    remaining = qty
    for row in _rows_for_variant(db, variant_id):
        if remaining <= 0:
            break
        reserved = int(row.reserved or 0)
        if reserved <= 0:
            continue
        take = min(reserved, remaining)
        row.reserved = reserved - take
        remaining -= take


def consume_variant(db: Session, variant_id: int, qty: int) -> None:
    """Fulfil a reservation: drop both on_hand and reserved (stock shipped out)."""
    if qty <= 0:
        return
    remaining = qty
    for row in _rows_for_variant(db, variant_id):
        if remaining <= 0:
            break
        on_hand = int(row.on_hand or 0)
        if on_hand <= 0:
            continue
        take = min(on_hand, remaining)
        row.on_hand = on_hand - take
        row.reserved = max(0, int(row.reserved or 0) - take)
        remaining -= take


def available_by_variant(db: Session, variant_ids: Iterable[int]) -> dict[int, int]:
    """Unreserved warehouse stock (``on_hand - reserved``) per variant, all warehouses."""
    ids = list({v for v in variant_ids if v})
    if not ids:
        return {}
    rows = db.execute(
        select(
            WarehouseInventory.variant_id,
            func.sum(WarehouseInventory.on_hand - WarehouseInventory.reserved),
        )
        .where(WarehouseInventory.variant_id.in_(ids))
        .group_by(WarehouseInventory.variant_id)
    ).all()
    return {int(vid): max(0, int(qty or 0)) for vid, qty in rows}


def available_qty_expr(variant_id_col):
    """Correlated subquery: unreserved warehouse stock for ``variant_id_col``."""
    return (
        select(
            func.coalesce(func.sum(WarehouseInventory.on_hand - WarehouseInventory.reserved), 0)
        )
        .where(WarehouseInventory.variant_id == variant_id_col)
        .scalar_subquery()
    )


def take_variant(db: Session, variant_id: int, qty: int) -> int:
    """Sell unreserved warehouse stock now (store counter sale). Returns units taken.

    Only ``on_hand`` drops: stock held for placed orders is never sold over.
    """
    if qty <= 0:
        return 0
    remaining = qty
    for row in _rows_for_variant(db, variant_id):
        if remaining <= 0:
            break
        free = int(row.on_hand or 0) - int(row.reserved or 0)
        if free <= 0:
            continue
        take = min(free, remaining)
        row.on_hand = int(row.on_hand or 0) - take
        remaining -= take
    return qty - remaining


def reserve_order_lines(db: Session, lines: Iterable[Line]) -> None:
    for variant_id, qty in lines:
        if variant_id:
            reserve_variant(db, variant_id, qty)


def consume_order_lines(db: Session, lines: Iterable[Line]) -> None:
    for variant_id, qty in lines:
        if variant_id:
            consume_variant(db, variant_id, qty)


def release_order_lines(db: Session, lines: Iterable[Line]) -> None:
    for variant_id, qty in lines:
        if variant_id:
            release_variant(db, variant_id, qty)
