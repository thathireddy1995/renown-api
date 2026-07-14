"""Staff store appointments — /staff/store/appointments."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clinical import (
    STATUS_FROM_UI,
    TYPE_LABEL,
    appointment_eager,
    default_store,
    find_doctor_by_name,
    find_or_create_customer_by_name,
    parse_slot,
    staff_appointment_row,
)
from app.database import get_db
from app.deps import pagination, require_role, TokenPrincipal
from app.dto.clinical_dto import (
    AppointmentStatusIn,
    StaffAppointmentCreate,
    StaffAppointmentListResponse,
    StaffAppointmentOut,
)
from app.schemas import Appointment, Customer, Doctor, Store

router = APIRouter(
    prefix="/staff/store/appointments",
    tags=["staff-store-appointments"],
    dependencies=[Depends(require_role("store_manager"))],
)

TYPE_FROM_UI = {
    "eye test": "eye_test",
    "frame fitting": "fitting",
    "contact lens trial": "lens_trial",
    "eye_test": "eye_test",
    "fitting": "fitting",
    "lens_trial": "lens_trial",
}


def _digits(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _resolve_doctor(db: Session, name: str, store_id: int | None) -> Doctor:
    doctor = find_doctor_by_name(db, name)
    if doctor:
        return doctor
    doctor = Doctor(name=name.strip(), specialty="Optometrist", store_id=store_id)
    db.add(doctor)
    db.flush()
    return doctor


def _parse_staff_slot(date_str: str | None, time_str: str):
    raw = time_str.strip()
    lowered = raw.lower()
    day = date_str
    time_part = raw
    if lowered.startswith("today "):
        day = date.today().isoformat()
        time_part = raw.split(" ", 1)[1]
    elif lowered.startswith("tomorrow "):
        day = (date.today() + timedelta(days=1)).isoformat()
        time_part = raw.split(" ", 1)[1]
    elif " " in raw and len(raw.split(" ", 1)[0]) == 10:
        day, time_part = raw.split(" ", 1)
    if not day:
        day = date.today().isoformat()
    return parse_slot(day, time_part)


@router.get("", response_model=StaffAppointmentListResponse)
def list_appointments(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    store_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> StaffAppointmentListResponse:
    limit, offset = page
    sid = principal.store_id or store_id
    if sid is None:
        store = default_store(db)
        sid = store.id if store else None
    if sid is None:
        return StaffAppointmentListResponse(items=[], total=0, limit=limit, offset=offset)

    stmt = (
        select(Appointment)
        .options(*appointment_eager())
        .where(Appointment.store_id == sid)
    )
    count_stmt = (
        select(func.count())
        .select_from(Appointment)
        .where(Appointment.store_id == sid)
    )

    if status_filter:
        key = status_filter.strip().lower()
        mapped = STATUS_FROM_UI.get(key)
        if mapped:
            stmt = stmt.where(Appointment.status == mapped)
            count_stmt = count_stmt.where(Appointment.status == mapped)
        else:
            stmt = stmt.where(Appointment.status == status_filter)
            count_stmt = count_stmt.where(Appointment.status == status_filter)

    if search:
        q = f"%{search.strip()}%"
        stmt = (
            stmt.outerjoin(Customer, Appointment.customer_id == Customer.id)
            .outerjoin(Doctor, Appointment.doctor_id == Doctor.id)
            .where(
                or_(
                    Customer.name.ilike(q),
                    Appointment.phone.ilike(q),
                    Doctor.name.ilike(q),
                    func.concat("AP-", Appointment.id).ilike(q),
                )
            )
        )
        count_stmt = (
            select(func.count())
            .select_from(Appointment)
            .outerjoin(Customer, Appointment.customer_id == Customer.id)
            .outerjoin(Doctor, Appointment.doctor_id == Doctor.id)
            .where(Appointment.store_id == sid)
            .where(
                or_(
                    Customer.name.ilike(q),
                    Appointment.phone.ilike(q),
                    Doctor.name.ilike(q),
                    func.concat("AP-", Appointment.id).ilike(q),
                )
            )
        )

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Appointment.scheduled_at.asc()).limit(limit).offset(offset)
    ).all()
    return StaffAppointmentListResponse(
        items=[StaffAppointmentOut(**staff_appointment_row(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffAppointmentOut, status_code=status.HTTP_201_CREATED)
def create_appointment(
    body: StaffAppointmentCreate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffAppointmentOut:
    sid = principal.store_id or body.store_id
    store = db.get(Store, sid) if sid is not None else None
    if store is None:
        store = default_store(db)
    if store is None:
        raise HTTPException(status_code=400, detail="No store configured")

    phone = _digits(body.phone)
    if len(phone) < 10:
        raise HTTPException(status_code=422, detail="Enter a valid phone number")

    customer = find_or_create_customer_by_name(db, body.customer.strip(), phone)
    doctor = _resolve_doctor(db, body.doctor, store.id)

    appt_type = TYPE_FROM_UI.get(body.type.strip().lower(), "eye_test")
    if appt_type not in TYPE_LABEL:
        appt_type = "eye_test"

    status_key = STATUS_FROM_UI.get(body.status.strip().lower(), "booked")
    try:
        scheduled = _parse_staff_slot(body.date, body.time)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = Appointment(
        customer_id=customer.id if customer else None,
        store_id=store.id,
        doctor_id=doctor.id,
        appointment_type=appt_type,
        scheduled_at=scheduled,
        status=status_key,
        phone=phone,
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
    return StaffAppointmentOut(**staff_appointment_row(row))


@router.patch("/{appointment_ref}/status", response_model=StaffAppointmentOut)
def patch_status(
    appointment_ref: str,
    payload: AppointmentStatusIn,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffAppointmentOut:
    ref = appointment_ref.strip()
    numeric = ref[3:] if ref.upper().startswith("AP-") else ref
    if not numeric.isdigit():
        raise HTTPException(status_code=404, detail="Appointment not found")

    row = db.scalar(
        select(Appointment)
        .options(*appointment_eager())
        .where(Appointment.id == int(numeric))
    )
    if not row:
        raise HTTPException(status_code=404, detail="Appointment not found")

    mapped = STATUS_FROM_UI.get(payload.status.strip().lower())
    if not mapped:
        raise HTTPException(status_code=400, detail="Invalid status")
    row.status = mapped
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
    return StaffAppointmentOut(**staff_appointment_row(row))
