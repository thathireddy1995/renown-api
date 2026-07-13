"""Staff store appointments — /staff/store/appointments."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clinical import (
    STATUS_FROM_UI,
    appointment_eager,
    default_store,
    staff_appointment_row,
)
from app.database import get_db
from app.deps import get_current_store_staff, pagination
from app.dto.clinical_dto import (
    AppointmentStatusIn,
    StaffAppointmentListResponse,
    StaffAppointmentOut,
)
from app.schemas import Appointment, Customer, Doctor, User

router = APIRouter(prefix="/staff/store/appointments", tags=["staff-store-appointments"])


@router.get("", response_model=StaffAppointmentListResponse)
def list_appointments(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_store_staff),
    page: tuple[int, int] = Depends(pagination),
    store_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> StaffAppointmentListResponse:
    limit, offset = page
    sid = store_id
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


@router.patch("/{appointment_ref}/status", response_model=StaffAppointmentOut)
def patch_status(
    appointment_ref: str,
    payload: AppointmentStatusIn,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_store_staff),
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
