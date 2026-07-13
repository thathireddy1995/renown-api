"""Customer appointments — /customer/appointments."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clinical import (
    appointment_eager,
    customer_appointment_row,
    doctor_out,
    parse_doctor_id,
    parse_slot,
    resolve_store,
)
from app.database import get_db
from app.deps import get_current_customer, pagination
from app.dto.clinical_dto import (
    BookAppointmentIn,
    CustomerAppointmentListResponse,
    CustomerAppointmentOut,
    DoctorListResponse,
    DoctorOut,
)
from app.schemas import Appointment, Customer, Doctor

router = APIRouter(prefix="/customer/appointments", tags=["customer-appointments"])


@router.get("/doctors", response_model=DoctorListResponse)
def list_doctors(
    store_id: int | None = None,
    db: Session = Depends(get_db),
) -> DoctorListResponse:
    stmt = select(Doctor).order_by(Doctor.id.asc())
    if store_id is not None:
        stmt = stmt.where(
            or_(Doctor.store_id == store_id, Doctor.store_id.is_(None))
        )
    rows = db.scalars(stmt).all()
    return DoctorListResponse(items=[DoctorOut(**doctor_out(r)) for r in rows])


@router.get("/", response_model=CustomerAppointmentListResponse)
def list_my_appointments(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
    page: tuple[int, int] = Depends(pagination),
) -> CustomerAppointmentListResponse:
    limit, offset = page
    base = select(Appointment).where(Appointment.customer_id == customer.id)
    total = db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0
    rows = db.scalars(
        base.options(*appointment_eager())
        .order_by(Appointment.scheduled_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return CustomerAppointmentListResponse(
        items=[CustomerAppointmentOut(**customer_appointment_row(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/", response_model=CustomerAppointmentOut, status_code=status.HTTP_201_CREATED)
def book_appointment(
    payload: BookAppointmentIn,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CustomerAppointmentOut:
    store = resolve_store(db, payload.store_id, payload.store)
    if not store:
        raise HTTPException(status_code=400, detail="No store available for booking")

    doc_id = parse_doctor_id(payload.doctor_id)
    doctor = db.get(Doctor, doc_id) if doc_id is not None else None
    if not doctor:
        raise HTTPException(status_code=400, detail="Doctor not found")

    try:
        scheduled = parse_slot(payload.date, payload.time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    appt_type = payload.appointment_type if payload.appointment_type in {
        "eye_test", "fitting", "lens_trial"
    } else "eye_test"

    row = Appointment(
        customer_id=customer.id,
        store_id=store.id,
        doctor_id=doctor.id,
        appointment_type=appt_type,
        scheduled_at=scheduled,
        status="booked",
        phone=payload.phone or customer.phone,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    row = db.scalar(
        select(Appointment)
        .options(*appointment_eager())
        .where(Appointment.id == row.id)
    )
    return CustomerAppointmentOut(**customer_appointment_row(row))
