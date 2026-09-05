"""Lens-fit helpers for warehouse/store order views."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.schemas import Order


def first_lens_fit(order: Order) -> dict | None:
    for item in order.items or []:
        fit = getattr(item, "lens_fit", None)
        if isinstance(fit, dict) and fit:
            return fit
    return None


def line_items_from_order(order: Order) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in order.items or []:
        product = getattr(item, "product", None)
        name = (item.name_snapshot or (product.name if product else None) or "Item").strip()
        rows.append(
            {
                "name": name,
                "qty": int(item.qty or 0),
                "lensFit": item.lens_fit if isinstance(item.lens_fit, dict) else None,
            }
        )
    return rows


def lens_fits_by_order_numbers(db: Session, numbers: list[str]) -> dict[str, dict | None]:
    """Batch-load first lens_fit per web order_number (one query, not N+1)."""
    unique = [n for n in dict.fromkeys(numbers) if n]
    if not unique:
        return {}
    rows = db.scalars(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.order_number.in_(unique))
    ).all()
    out: dict[str, dict | None] = {n: None for n in unique}
    for row in rows:
        out[row.order_number] = first_lens_fit(row)
    return out


def labels_from_lens_fit(fit: dict | None) -> tuple[str, str]:
    """Return (lens_type, power_label) for store order lists."""
    if not isinstance(fit, dict):
        return "", ""
    lens = str(fit.get("lensType") or fit.get("lens_type") or "").strip()
    file = fit.get("prescriptionFile") or fit.get("prescription_file") or {}
    if isinstance(file, dict) and (file.get("url") or file.get("name")):
        name = str(file.get("name") or "prescription").strip()
        return lens, f"Uploaded Rx · {name}" if name else "Uploaded Rx"
    mode = str(fit.get("powerMode") or fit.get("power_mode") or "").strip().lower()
    if mode == "zero":
        return lens, "Zero power"
    rx = fit.get("prescription") or {}
    right = rx.get("right") if isinstance(rx, dict) else {}
    left = rx.get("left") if isinstance(rx, dict) else {}
    if not isinstance(right, dict):
        right = {}
    if not isinstance(left, dict):
        left = {}
    parts: list[str] = []
    rs = str(right.get("sph") or "").strip()
    ls = str(left.get("sph") or "").strip()
    if rs:
        parts.append(f"R {rs}")
    if ls:
        parts.append(f"L {ls}")
    return lens, " / ".join(parts)
