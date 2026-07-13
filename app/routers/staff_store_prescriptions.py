"""Staff store prescriptions — /staff/store/prescriptions."""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.clinical import (
    default_store,
    find_doctor_by_name,
    find_or_create_customer_by_name,
    prescription_eager,
    staff_prescription_row,
)
from app.database import get_db
from app.deps import pagination, require_role, TokenPrincipal
from app.dto.clinical_dto import (
    StaffPrescriptionCreate,
    StaffPrescriptionListResponse,
    StaffPrescriptionOut,
)
from app.schemas import Customer, Doctor, Prescription

router = APIRouter(prefix="/staff/store/prescriptions", tags=["staff-store-prescriptions"], dependencies=[Depends(require_role("store_manager"))])


@router.get("", response_model=StaffPrescriptionListResponse)
def list_prescriptions(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    store_id: int | None = None,
    search: str | None = Query(None, alias="q"),
) -> StaffPrescriptionListResponse:
    """List prescriptions with customer/doctor joined in one query.

    Optional store_id scopes to doctors assigned to that store (or unassigned).
    """
    limit, offset = page
    sid = principal.store_id or store_id
    if sid is None:
        store = default_store(db)
        sid = store.id if store else None

    stmt = select(Prescription).options(*prescription_eager())
    count_stmt = select(func.count()).select_from(Prescription)

    if sid is not None:
        stmt = stmt.outerjoin(Doctor, Prescription.doctor_id == Doctor.id).where(
            or_(Doctor.store_id == sid, Doctor.store_id.is_(None), Prescription.doctor_id.is_(None))
        )
        count_stmt = (
            select(func.count())
            .select_from(Prescription)
            .outerjoin(Doctor, Prescription.doctor_id == Doctor.id)
            .where(
                or_(
                    Doctor.store_id == sid,
                    Doctor.store_id.is_(None),
                    Prescription.doctor_id.is_(None),
                )
            )
        )

    if search:
        q = f"%{search.strip()}%"
        # Re-join carefully when store filter already joined Doctor
        if sid is None:
            stmt = stmt.outerjoin(Doctor, Prescription.doctor_id == Doctor.id)
            count_stmt = count_stmt.outerjoin(Doctor, Prescription.doctor_id == Doctor.id)
        stmt = stmt.join(Customer, Prescription.customer_id == Customer.id).where(
            or_(
                Customer.name.ilike(q),
                Doctor.name.ilike(q),
                func.concat("RX-", Prescription.id).ilike(q),
            )
        )
        count_stmt = (
            count_stmt.join(Customer, Prescription.customer_id == Customer.id).where(
                or_(
                    Customer.name.ilike(q),
                    Doctor.name.ilike(q),
                    func.concat("RX-", Prescription.id).ilike(q),
                )
            )
        )

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Prescription.id.desc()).limit(limit).offset(offset)
    ).all()
    return StaffPrescriptionListResponse(
        items=[StaffPrescriptionOut(**staff_prescription_row(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffPrescriptionOut, status_code=status.HTTP_201_CREATED)
def create_prescription(
    payload: StaffPrescriptionCreate,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffPrescriptionOut:
    customer = None
    if payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
    if not customer:
        customer = find_or_create_customer_by_name(db, payload.customer, payload.phone)
    if not customer:
        raise HTTPException(status_code=400, detail="Customer is required")

    doctor = None
    if payload.doctor_id is not None:
        doctor = db.get(Doctor, payload.doctor_id)
    if not doctor and payload.doctor:
        doctor = find_doctor_by_name(db, payload.doctor)

    recorded = None
    if payload.date:
        try:
            recorded = date.fromisoformat(payload.date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid date") from exc
    else:
        recorded = datetime.utcnow().date()

    row = Prescription(
        customer_id=customer.id,
        doctor_id=doctor.id if doctor else None,
        right_sph=payload.sphR,
        right_cyl=payload.cylR,
        left_sph=payload.sphL,
        left_cyl=payload.cylL,
        pd=payload.pd,
        recorded_at=recorded,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    row = db.scalar(
        select(Prescription)
        .options(*prescription_eager())
        .where(Prescription.id == row.id)
    )
    return StaffPrescriptionOut(**staff_prescription_row(row))
