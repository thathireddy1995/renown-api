"""Shared helpers for appointments / prescriptions display shaping."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.schemas import Appointment, Customer, Doctor, Prescription, Store

TYPE_LABEL = {
    "eye_test": "Eye Test",
    "fitting": "Frame Fitting",
    "lens_trial": "Contact Lens Trial",
}

STATUS_STAFF = {
    "booked": "Pending",
    "confirmed": "Confirmed",
    "completed": "Completed",
    "cancelled": "Cancelled",
}

STATUS_FROM_UI = {
    "pending": "booked",
    "confirmed": "confirmed",
    "completed": "completed",
    "cancelled": "cancelled",
    "booked": "booked",
}

DOCTOR_YEARS = {
    "Dr. Amara Rao": 12,
    "Dr. Julien Weiss": 8,
    "Dr. Naomi Chen": 15,
    "Dr. Kapoor": 14,
    "Dr. Bhatt": 9,
    "Rakesh": 6,
}

CITY_ALIASES = {
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "delhi": "new delhi",
    "new delhi": "new delhi",
}


def doctor_out(row: Doctor) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "title": row.specialty or "Optometrist",
        "years": DOCTOR_YEARS.get(row.name, 10),
    }


def format_slot(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    today = datetime.now(local.tzinfo).date()
    d = local.date()
    t = local.strftime("%H:%M")
    if d == today:
        return f"Today {t}"
    if d.toordinal() == today.toordinal() + 1:
        return f"Tomorrow {t}"
    return f"{d.isoformat()} {t}"


def customer_appointment_row(row: Appointment) -> dict:
    store_name = row.store.city if row.store and row.store.city else (
        row.store.name if row.store else ""
    )
    doctor_name = row.doctor.name if row.doctor else "—"
    scheduled = row.scheduled_at
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    local = scheduled.astimezone()
    return {
        "id": f"apt-{row.id}",
        "store": store_name,
        "doctor": doctor_name,
        "date": local.date().isoformat(),
        "time": local.strftime("%I:%M %p").lstrip("0"),
    }


def staff_appointment_row(row: Appointment) -> dict:
    customer = (
        row.customer.name
        if row.customer and row.customer.name
        else (row.phone or "Walk-in")
    )
    phone = row.phone or (row.customer.phone if row.customer else "") or "—"
    return {
        "id": f"AP-{row.id}",
        "time": format_slot(row.scheduled_at),
        "customer": customer,
        "phone": phone,
        "type": TYPE_LABEL.get(row.appointment_type, row.appointment_type),
        "doctor": row.doctor.name if row.doctor else "—",
        "status": STATUS_STAFF.get(row.status, row.status),
    }


def staff_prescription_row(row: Prescription) -> dict:
    return {
        "id": f"RX-{row.id}",
        "customer": row.customer.name if row.customer and row.customer.name else "—",
        "date": (row.recorded_at or (row.created_at.date() if row.created_at else date.today())).isoformat(),
        "sphR": row.right_sph or "0",
        "cylR": row.right_cyl or "0",
        "sphL": row.left_sph or "0",
        "cylL": row.left_cyl or "0",
        "pd": row.pd or "—",
        "doctor": row.doctor.name if row.doctor else "—",
    }


def appointment_eager():
    return (
        joinedload(Appointment.customer),
        joinedload(Appointment.doctor),
        joinedload(Appointment.store),
    )


def prescription_eager():
    return (joinedload(Prescription.customer), joinedload(Prescription.doctor))


def default_store(db: Session) -> Store | None:
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


def resolve_store(db: Session, store_id: int | None, store_label: str | None) -> Store | None:
    if store_id is not None:
        row = db.get(Store, store_id)
        if row:
            return row
    if store_label:
        needle = CITY_ALIASES.get(store_label.strip().lower(), store_label.strip().lower())
        rows = db.scalars(select(Store).order_by(Store.id.asc())).all()
        for s in rows:
            city = (s.city or "").strip().lower()
            name = (s.name or "").strip().lower()
            alias = CITY_ALIASES.get(city, city)
            if needle in (city, alias) or needle in name:
                return s
        for s in rows:
            if store_label.strip().lower() in (s.name or "").lower():
                return s
    return default_store(db)


def parse_doctor_id(raw: int | str) -> int | None:
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text.isdigit():
        return int(text)
    if text.startswith("d-") and text[2:].isdigit():
        return int(text[2:])
    return None


def parse_slot(date_str: str, time_str: str) -> datetime:
    """Parse UI date (YYYY-MM-DD) + time like '10:00 AM' into UTC-aware datetime."""
    cleaned = time_str.strip().upper().replace(".", "")
    for fmt in ("%Y-%m-%d %I:%M %p", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.strptime(f"{date_str} {cleaned}", fmt)
            return naive.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Invalid date/time: {date_str} {time_str}")


def find_or_create_customer_by_name(
    db: Session, name: str | None, phone: str | None
) -> Customer | None:
    if phone:
        existing = db.scalar(select(Customer).where(Customer.phone == phone))
        if existing:
            if name and not existing.name:
                existing.name = name
            return existing
    if name:
        existing = db.scalar(
            select(Customer).where(func.lower(Customer.name) == name.strip().lower())
        )
        if existing:
            return existing
    if not name and not phone:
        return None
    row = Customer(
        name=name,
        phone=phone or f"walkin-{int(datetime.now(timezone.utc).timestamp())}",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def find_doctor_by_name(db: Session, name: str | None) -> Doctor | None:
    if not name:
        return None
    return db.scalar(
        select(Doctor).where(func.lower(Doctor.name) == name.strip().lower())
    )
