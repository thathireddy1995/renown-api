"""Admin Cashbook ledger: manual entries + sales / refunds read live from orders.

Three round trips per load regardless of size (entries, opening balance, stores).
Every filter column is indexed: cashbook_entries(entry_date / store_id),
store_orders.created_at, orders.created_at, orders.status.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.ist import end_of_day, start_of_day
from app.dto.cashbook_dto import CashbookEntryOut, CashbookResponse, CashbookStoreOut

# Website orders have no store; they sit under this bucket in the store filter.
ONLINE = "online"

_MANUAL = """
    SELECT 'm-' || e.id AS id, 'manual' AS source, e.store_id,
           coalesce(s.name, 'Online / Head office') AS store_name,
           e.entry_date AS entry_day, to_char(e.created_at, 'HH24:MI') AS entry_time,
           e.entry_type AS type, e.category, e.mode, e.amount,
           coalesce(e.note, '') AS note, coalesce(e.entered_by_name, 'Admin') AS entered_by
    FROM cashbook_entries e
    LEFT JOIN stores s ON s.id = e.store_id
    WHERE {date_cond} AND {store_cond}
"""

_STORE_SALES = """
    SELECT 's-' || o.id, 'store_sale', o.store_id, s.name,
           o.created_at::date, to_char(o.created_at, 'HH24:MI'),
           'in', 'Store sales',
           CASE lower(o.payment_method) WHEN 'cash' THEN 'Cash' WHEN 'card' THEN 'Card'
                WHEN 'upi' THEN 'UPI' ELSE 'Online' END,
           o.total, 'Bill ' || o.order_number, coalesce(o.associate_name, 'Store')
    FROM store_orders o
    JOIN stores s ON s.id = o.store_id
    WHERE {ts_cond} AND {store_cond}
      AND lower(o.status) NOT IN ('cancelled', 'missed', 'void')
      AND o.total > 0
      AND NOT EXISTS (SELECT 1 FROM orders w WHERE w.order_number = o.order_number)
"""

# Prepaid web orders are money received on order; COD only once delivered.
_WEB_SALES = """
    SELECT 'w-' || o.id, 'online_sale', NULL::int, 'Online',
           o.created_at::date, to_char(o.created_at, 'HH24:MI'),
           'in', 'Online sales',
           CASE WHEN o.payment_method = 'cod' THEN 'Cash' ELSE 'Online' END,
           o.total, 'Order ' || o.order_number, 'Website'
    FROM orders o
    WHERE {ts_cond}
      AND o.total > 0
      AND ((o.payment_method <> 'cod' AND o.payment_status = 'paid')
           OR (o.payment_method = 'cod' AND o.status = 'delivered'))
"""

# Paid web orders cancelled later are refunded; updated_at is the cancel date.
_REFUNDS = """
    SELECT 'r-' || o.id, 'refund', NULL::int, 'Online',
           o.updated_at::date, to_char(o.updated_at, 'HH24:MI'),
           'out', 'Refund', 'Online',
           o.total, 'Cancelled order ' || o.order_number, 'Website'
    FROM orders o
    WHERE o.status = 'cancelled' AND o.payment_status = 'paid' AND o.total > 0
      AND {ts_cond}
"""


def _union(store: str | int, *, before: bool) -> str:
    """UNION ALL of the ledger sources for this store filter.

    ``before`` = rows strictly before the range (opening balance); otherwise rows in range.
    Only fixed SQL fragments are concatenated — all values are bound parameters.
    """
    if before:
        date_cond = "{col} < :d_from"
        ts_cond = "{col} < :start"
    else:
        date_cond = "{col} BETWEEN :d_from AND :d_to"
        ts_cond = "{col} BETWEEN :start AND :end"

    if store == "all":
        manual_store, store_sales_store, include_store, include_web = "TRUE", "TRUE", True, True
    elif store == ONLINE:
        manual_store, store_sales_store, include_store, include_web = "e.store_id IS NULL", "", False, True
    else:
        manual_store, store_sales_store, include_store, include_web = (
            "e.store_id = :store_id",
            "o.store_id = :store_id",
            True,
            False,
        )

    parts = [_MANUAL.format(date_cond=date_cond.format(col="e.entry_date"), store_cond=manual_store)]
    if include_store:
        parts.append(
            _STORE_SALES.format(ts_cond=ts_cond.format(col="o.created_at"), store_cond=store_sales_store)
        )
    if include_web:
        parts.append(_WEB_SALES.format(ts_cond=ts_cond.format(col="o.created_at")))
        parts.append(_REFUNDS.format(ts_cond=ts_cond.format(col="o.updated_at")))
    return "\nUNION ALL\n".join(parts)


def build_cashbook(db: Session, date_from: date, date_to: date, store: str | int) -> CashbookResponse:
    params: dict[str, object] = {
        "d_from": date_from,
        "d_to": date_to,
        "start": start_of_day(date_from),
        "end": end_of_day(date_to),
    }
    if isinstance(store, int):
        params["store_id"] = store

    rows = db.execute(
        text(f"SELECT * FROM ({_union(store, before=False)}) x ORDER BY entry_day, entry_time, id"), params
    ).all()
    opening = db.execute(
        text(
            "SELECT coalesce(sum(CASE WHEN type = 'in' THEN amount ELSE -amount END), 0) "
            f"FROM ({_union(store, before=True)}) x"
        ),
        params,
    ).scalar_one()
    stores = db.execute(text("SELECT id, name FROM stores ORDER BY name")).all()

    return CashbookResponse(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        opening_balance=float(Decimal(opening or 0)),
        stores=[CashbookStoreOut(id=s.id, name=s.name) for s in stores],
        entries=[
            CashbookEntryOut(
                id=r.id,
                source=r.source,
                store_id=r.store_id,
                store=r.store_name or "",
                date=r.entry_day.isoformat(),
                time=r.entry_time or "",
                type=r.type,
                category=r.category,
                mode=r.mode,
                amount=float(r.amount),
                note=r.note or "",
                entered_by=r.entered_by or "",
            )
            for r in rows
        ],
    )
