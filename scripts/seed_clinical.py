"""Seed doctors, appointments, and prescriptions from customer/staff UI mocks.

Run after seed_locations + seed_customers:

    python -m scripts.seed_clinical

Safe to re-run — doctors matched by name; appointments/prescriptions by fixed ids.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text

from app.database import SessionLocal
from app.schemas import Appointment, Customer, Doctor, Prescription, Store

# Customer-facing optometrists (store_id NULL = all studios)
CUSTOMER_DOCTORS = [
    ("Dr. Amara Rao", "Senior Optometrist"),
    ("Dr. Julien Weiss", "Optometrist"),
    ("Dr. Naomi Chen", "Lead Optometrist"),
]

# Staff-side doctors used in Appointments / Prescriptions mocks
STAFF_DOCTORS = [
    ("Dr. Kapoor", "Senior Optometrist"),
    ("Dr. Bhatt", "Optometrist"),
    ("Rakesh", "Frame Specialist"),
]

# id, relative day (0=today), HH:MM, customer name, phone, type, doctor, status
APPOINTMENTS = [
    (501, 0, "10:30", "Sonal Mehta", "+91 99999 88888", "eye_test", "Dr. Kapoor", "confirmed"),
    (502, 0, "11:15", "Ajay Nair", "+91 98123 44444", "fitting", "Rakesh", "confirmed"),
    (503, 0, "12:00", "Divya Shah", "+91 96000 11111", "lens_trial", "Dr. Bhatt", "booked"),
    (504, 0, "14:00", "Manish Gupta", "+91 90090 33333", "eye_test", "Dr. Kapoor", "confirmed"),
    (505, 1, "10:00", "Priya Nambiar", "+91 95555 66666", "eye_test", "Dr. Kapoor", "confirmed"),
    (506, 1, "15:30", "Rahul Deshmukh", "+91 91112 22233", "eye_test", "Dr. Bhatt", "cancelled"),
]

# id, customer, date, sphR, cylR, sphL, cylL, pd, doctor
PRESCRIPTIONS = [
    (2201, "Rohit Verma", "2026-06-14", "-1.25", "-0.50", "-1.00", "-0.75", "62", "Dr. Kapoor"),
    (2202, "Neha Iyer", "2026-06-20", "+0.50", "0", "+0.25", "0", "60", "Dr. Bhatt"),
    (2203, "Ananya Bose", "2026-06-28", "-2.75", "-1.25", "-2.50", "-1.00", "63", "Dr. Kapoor"),
    (2204, "Vikram Rao", "2026-07-01", "-3.50", "-0.25", "-3.75", "-0.50", "65", "Dr. Bhatt"),
]


def _upsert_doctor(db, name: str, specialty: str, store_id: int | None) -> Doctor:
    row = db.scalar(select(Doctor).where(Doctor.name == name))
    if row:
        row.specialty = specialty
        if store_id is not None:
            row.store_id = store_id
        return row
    row = Doctor(name=name, specialty=specialty, store_id=store_id)
    db.add(row)
    db.flush()
    return row


def _upsert_customer(db, name: str, phone: str) -> Customer:
    digits = "".join(c for c in phone if c.isdigit())
    # Prefer unique phone keys for walk-in seeds
    phone_key = digits[-10:] if len(digits) >= 10 else digits or f"9{abs(hash(name)) % 10**9:09d}"
    row = db.scalar(select(Customer).where(Customer.phone == phone_key))
    if row:
        row.name = name
        row.is_active = True
        return row
    row = Customer(name=name, phone=phone_key, is_active=True)
    db.add(row)
    db.flush()
    return row


def seed() -> None:
    db = SessionLocal()
    try:
        store = db.scalar(
            select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
        ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))
        if not store:
            print("No stores — run seed_locations first")
            return

        for name, specialty in CUSTOMER_DOCTORS:
            _upsert_doctor(db, name, specialty, None)
            print(f"Doctor: {name}")

        doctors: dict[str, Doctor] = {}
        for name, specialty in STAFF_DOCTORS:
            doctors[name] = _upsert_doctor(db, name, specialty, store.id)
            print(f"Staff doctor: {name}")

        # Also index customer doctors by name
        for d in db.scalars(select(Doctor)).all():
            doctors[d.name] = d

        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        for (
            apt_id,
            day_offset,
            hhmm,
            cust_name,
            phone,
            apt_type,
            doc_name,
            status,
        ) in APPOINTMENTS:
            customer = _upsert_customer(db, cust_name, phone)
            hour, minute = map(int, hhmm.split(":"))
            scheduled = today + timedelta(days=day_offset, hours=hour, minutes=minute)
            doctor = doctors.get(doc_name)

            row = db.get(Appointment, apt_id)
            if row:
                row.customer_id = customer.id
                row.store_id = store.id
                row.doctor_id = doctor.id if doctor else None
                row.appointment_type = apt_type
                row.scheduled_at = scheduled
                row.status = status
                row.phone = phone
                print(f"Updated appointment AP-{apt_id}")
            else:
                db.add(
                    Appointment(
                        id=apt_id,
                        customer_id=customer.id,
                        store_id=store.id,
                        doctor_id=doctor.id if doctor else None,
                        appointment_type=apt_type,
                        scheduled_at=scheduled,
                        status=status,
                        phone=phone,
                    )
                )
                print(f"Created appointment AP-{apt_id}")

        for (
            rx_id,
            cust_name,
            date_str,
            sph_r,
            cyl_r,
            sph_l,
            cyl_l,
            pd,
            doc_name,
        ) in PRESCRIPTIONS:
            customer = _upsert_customer(db, cust_name, f"rx-{rx_id}")
            doctor = doctors.get(doc_name)
            recorded = date.fromisoformat(date_str)
            row = db.get(Prescription, rx_id)
            if row:
                row.customer_id = customer.id
                row.doctor_id = doctor.id if doctor else None
                row.right_sph = sph_r
                row.right_cyl = cyl_r
                row.left_sph = sph_l
                row.left_cyl = cyl_l
                row.pd = pd
                row.recorded_at = recorded
                print(f"Updated prescription RX-{rx_id}")
            else:
                db.add(
                    Prescription(
                        id=rx_id,
                        customer_id=customer.id,
                        doctor_id=doctor.id if doctor else None,
                        right_sph=sph_r,
                        right_cyl=cyl_r,
                        left_sph=sph_l,
                        left_cyl=cyl_l,
                        pd=pd,
                        recorded_at=recorded,
                    )
                )
                print(f"Created prescription RX-{rx_id}")

        db.commit()

        # Bump sequences past explicit ids
        db.execute(text(
            "SELECT setval(pg_get_serial_sequence('appointments', 'id'), "
            "GREATEST((SELECT COALESCE(MAX(id), 1) FROM appointments), 1))"
        ))
        db.execute(text(
            "SELECT setval(pg_get_serial_sequence('prescriptions', 'id'), "
            "GREATEST((SELECT COALESCE(MAX(id), 1) FROM prescriptions), 1))"
        ))
        db.commit()
        print("Clinical seed complete")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
