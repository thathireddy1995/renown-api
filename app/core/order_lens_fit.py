"""Lens-fit helpers for warehouse/store order views."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.s3_images import public_url_for
from app.schemas import Order, OrderItem, StoreOrder, StoreOrderItem

EYE_FIELDS = ("sph", "cyl", "axis", "pd", "add")
POWER_MODES = ("powered", "zero", "progressive", "frame_only")
FIT_SOURCES = ("manual", "saved", "upload", "later")


def clean_eye(raw: object) -> dict[str, str]:
    src = raw if isinstance(raw, dict) else {}
    return {k: str(src.get(k) or "").strip()[:20] for k in EYE_FIELDS}


def own_prescription_file(raw: object, customer_id: int) -> dict[str, str] | None:
    """Only accept files uploaded for this customer through our presign flow."""
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key") or "").strip()
    if not key.startswith(f"catalog/prescriptions/{customer_id}/") or ".." in key:
        return None
    return {
        "url": public_url_for(key),
        "key": key,
        "name": str(raw.get("name") or "prescription").strip()[:200],
        "contentType": str(raw.get("contentType") or "").strip()[:80],
    }


def clean_patient(raw: object) -> dict[str, str] | None:
    if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
        return None
    out = {"name": str(raw["name"]).strip()[:120]}
    if raw.get("phone"):
        out["phone"] = str(raw["phone"]).strip()[:20]
    return out


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def sanitize_lens_fit(raw: object, customer_id: int) -> dict:
    """Validate a client lens_fit (counter orders) and keep only known fields."""
    if not isinstance(raw, dict):
        raise _unprocessable("Lens details are missing.")
    mode = str(raw.get("powerMode") or "").strip().lower()
    if mode not in POWER_MODES:
        raise _unprocessable("Choose single vision, zero power, progressive or frame only.")
    if mode == "frame_only":
        return {"powerMode": mode, "lensType": "Frame only"}
    lens_type = str(raw.get("lensType") or "").strip()[:120]
    if not lens_type:
        raise _unprocessable("Choose a lens.")
    if mode == "zero":
        return {"powerMode": mode, "lensType": lens_type}

    source = str(raw.get("source") or "").strip().lower()
    if source not in FIT_SOURCES:
        raise _unprocessable("Add the power, upload the Rx, or mark it to follow later.")
    fit: dict = {"powerMode": mode, "lensType": lens_type, "source": source}
    patient = clean_patient(raw.get("patient"))
    if patient:
        fit["patient"] = patient
    if source == "later":
        return fit
    if source == "upload":
        file = own_prescription_file(raw.get("prescriptionFile"), customer_id)
        if file is None:
            raise _unprocessable("Upload the prescription photo or PDF again.")
        fit["prescriptionFile"] = file
        return fit
    rx = raw.get("prescription") if isinstance(raw.get("prescription"), dict) else {}
    right = clean_eye(rx.get("right"))
    left = clean_eye(rx.get("left"))
    if not right["sph"] or not left["sph"]:
        raise _unprocessable("Add SPH for both eyes.")
    if mode == "progressive" and (not right["add"] or not left["add"]):
        raise _unprocessable("Progressive lenses need ADD for both eyes.")
    fit["prescription"] = {"right": right, "left": left}
    return fit


def recent_lens_fits(db: Session, customer_id: int, limit: int = 12) -> list[dict]:
    """Typed prescriptions from this customer's latest counter and web orders."""
    store_fits = db.scalars(
        select(StoreOrderItem.lens_fit)
        .join(StoreOrder, StoreOrder.id == StoreOrderItem.store_order_id)
        .where(StoreOrder.customer_id == customer_id, StoreOrderItem.lens_fit.is_not(None))
        .order_by(StoreOrderItem.id.desc())
        .limit(limit)
    ).all() + db.scalars(
        select(StoreOrder.lens_fit)
        .where(StoreOrder.customer_id == customer_id, StoreOrder.lens_fit.is_not(None))
        .order_by(StoreOrder.id.desc())
        .limit(limit)
    ).all()
    web_fits = db.scalars(
        select(OrderItem.lens_fit)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.customer_id == customer_id, OrderItem.lens_fit.is_not(None))
        .order_by(Order.id.desc())
        .limit(limit)
    ).all()
    out: list[dict] = []
    for fit in [*store_fits, *web_fits]:
        if not isinstance(fit, dict) or not isinstance(fit.get("prescription"), dict):
            continue
        if str(fit.get("powerMode") or "").lower() not in ("powered", "progressive"):
            continue
        out.append(
            {
                "powerMode": fit.get("powerMode"),
                "patient": clean_patient(fit.get("patient")),
                "prescription": {
                    "right": clean_eye(fit["prescription"].get("right")),
                    "left": clean_eye(fit["prescription"].get("left")),
                },
            }
        )
    return out


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
    mode = str(fit.get("powerMode") or fit.get("power_mode") or "").strip().lower()
    if mode == "frame_only":
        return lens or "Frame only", "Frame only"
    patient = fit.get("patient")
    who = str(patient.get("name") or "").strip() if isinstance(patient, dict) else ""
    suffix = f" · for {who}" if who else ""
    prefix = "Progressive · " if mode == "progressive" else ""
    file = fit.get("prescriptionFile") or fit.get("prescription_file") or {}
    if isinstance(file, dict) and (file.get("url") or file.get("name")):
        name = str(file.get("name") or "prescription").strip()
        return lens, f"{prefix}Uploaded Rx · {name}{suffix}" if name else f"{prefix}Uploaded Rx{suffix}"
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
    if not parts and str(fit.get("source") or "").strip().lower() == "later":
        return lens, f"{prefix}Power to follow{suffix}"
    return lens, f"{prefix}{' / '.join(parts)}{suffix}" if parts else ""


def _fit(raw: object) -> dict | None:
    return raw if isinstance(raw, dict) and raw else None


def store_item_fits(order: StoreOrder) -> list[tuple[StoreOrderItem, dict | None]]:
    """Lens fit per counter-order line. Orders placed before per-line fits keep
    theirs on StoreOrder.lens_fit, which belongs to the first line."""
    items = sorted(order.items or [], key=lambda i: i.id or 0)
    if any(_fit(i.lens_fit) for i in items):
        return [(i, _fit(i.lens_fit)) for i in items]
    legacy = _fit(order.lens_fit)
    return [(i, legacy if n == 0 else None) for n, i in enumerate(items)]


def is_power_later(fit: dict | None) -> bool:
    return bool(fit) and str(fit.get("source") or "").lower() == "later"


def store_order_notes(fits: list[dict | None]) -> str | None:
    parts = [notes_from_fit(f) for f in fits if f]
    return " | ".join(p for p in parts if p)[:500] or None


def notes_from_fit(fit: dict) -> str | None:
    """StoreOrder.notes text ("lens · power") for a structured lens_fit."""
    lens, power = labels_from_lens_fit(fit)
    return " · ".join(dict.fromkeys(p for p in [lens, power] if p))[:500] or None
