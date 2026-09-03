"""Helpers for the one-Rx-per-customer saved profile."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ist import format_ist_datetime, now as ist_now
from app.dto.prescription_dto import (
    CustomerPrescriptionOut,
    CustomerPrescriptionUpsert,
    EyeRxIn,
)
from app.schemas import CustomerPrescription


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def summary_for(row: CustomerPrescription | None) -> str:
    if row is None:
        return ""
    if (row.power_mode or "").lower() == "zero":
        return "Zero power"
    right = " ".join(p for p in [row.right_sph, row.right_cyl, row.right_axis and f"@{row.right_axis}"] if p)
    left = " ".join(p for p in [row.left_sph, row.left_cyl, row.left_axis and f"@{row.left_axis}"] if p)
    parts: list[str] = []
    if right:
        parts.append(f"R {right}")
    if left:
        parts.append(f"L {left}")
    pd_parts = [p for p in [row.right_pd, row.left_pd] if p]
    if pd_parts:
        if row.right_pd and row.left_pd and row.right_pd == row.left_pd:
            parts.append(f"PD {row.right_pd}")
        else:
            parts.append(f"PD {'/'.join(pd_parts)}")
    return " / ".join(parts) if parts else ""


def to_out(row: CustomerPrescription) -> CustomerPrescriptionOut:
    return CustomerPrescriptionOut(
        id=row.id,
        customer_id=row.customer_id,
        power_mode=row.power_mode or "powered",
        vision_type=row.vision_type or "single_vision",
        lens_type=row.lens_type,
        right=EyeRxIn(
            sph=row.right_sph or "",
            cyl=row.right_cyl or "",
            axis=row.right_axis or "",
            pd=row.right_pd or "",
            add=row.right_add or "",
        ),
        left=EyeRxIn(
            sph=row.left_sph or "",
            cyl=row.left_cyl or "",
            axis=row.left_axis or "",
            pd=row.left_pd or "",
            add=row.left_add or "",
        ),
        power_summary=summary_for(row),
        updated_at=format_ist_datetime(row.updated_at) if row.updated_at else None,
    )


def get_for_customer(db: Session, customer_id: int) -> CustomerPrescription | None:
    return db.scalar(
        select(CustomerPrescription).where(CustomerPrescription.customer_id == customer_id)
    )


def upsert_for_customer(
    db: Session,
    customer_id: int,
    payload: CustomerPrescriptionUpsert,
) -> CustomerPrescription:
    mode = (payload.power_mode or "powered").strip().lower()
    if mode not in ("powered", "zero"):
        mode = "powered"
    vision = (payload.vision_type or "single_vision").strip() or "single_vision"
    right = payload.right or EyeRxIn()
    left = payload.left or EyeRxIn()

    row = get_for_customer(db, customer_id)
    if row is None:
        row = CustomerPrescription(customer_id=customer_id)
        db.add(row)

    row.power_mode = mode
    row.vision_type = vision
    row.lens_type = _clean(payload.lens_type)
    row.right_sph = _clean(right.sph)
    row.right_cyl = _clean(right.cyl)
    row.right_axis = _clean(right.axis)
    row.right_pd = _clean(right.pd)
    row.right_add = _clean(right.add)
    row.left_sph = _clean(left.sph)
    row.left_cyl = _clean(left.cyl)
    row.left_axis = _clean(left.axis)
    row.left_pd = _clean(left.pd)
    row.left_add = _clean(left.add)
    row.updated_at = ist_now()
    db.flush()
    return row


def upsert_from_lens_fit(db: Session, customer_id: int, lens_fit: Any) -> CustomerPrescription | None:
    """Persist Rx from cart/order lens_fit JSON. Returns None if nothing usable."""
    if not isinstance(lens_fit, dict):
        return None
    power_mode = str(lens_fit.get("powerMode") or lens_fit.get("power_mode") or "").strip().lower()
    if power_mode not in ("powered", "zero"):
        return None
    lens_type = lens_fit.get("lensType") or lens_fit.get("lens_type")
    rx = lens_fit.get("prescription") or {}
    right = rx.get("right") if isinstance(rx, dict) else {}
    left = rx.get("left") if isinstance(rx, dict) else {}
    if not isinstance(right, dict):
        right = {}
    if not isinstance(left, dict):
        left = {}

    payload = CustomerPrescriptionUpsert(
        power_mode=power_mode,
        vision_type="single_vision",
        lens_type=str(lens_type) if lens_type else None,
        right=EyeRxIn(
            sph=str(right.get("sph") or ""),
            cyl=str(right.get("cyl") or ""),
            axis=str(right.get("axis") or ""),
            pd=str(right.get("pd") or ""),
            add=str(right.get("add") or ""),
        ),
        left=EyeRxIn(
            sph=str(left.get("sph") or ""),
            cyl=str(left.get("cyl") or ""),
            axis=str(left.get("axis") or ""),
            pd=str(left.get("pd") or ""),
            add=str(left.get("add") or ""),
        ),
    )
    return upsert_for_customer(db, customer_id, payload)


def upsert_from_cart_lines(db: Session, customer_id: int, line_rows: list[Any]) -> None:
    """Save the first powered (else first zero) lens_fit found on cart lines."""
    zero_fit = None
    for row in line_rows:
        fit = getattr(row, "lens_fit", None)
        if not isinstance(fit, dict):
            continue
        mode = str(fit.get("powerMode") or fit.get("power_mode") or "").strip().lower()
        if mode == "powered":
            upsert_from_lens_fit(db, customer_id, fit)
            return
        if mode == "zero" and zero_fit is None:
            zero_fit = fit
    if zero_fit is not None:
        upsert_from_lens_fit(db, customer_id, zero_fit)
