"""Staff store directory — /staff/store/staff."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import TokenPrincipal, require_role
from app.core.employees import employee_eager, parse_status, staff_employee_row
from app.database import get_db
from app.deps import pagination
from app.dto.employee_dto import (
    StaffEmployeeCreate,
    StaffEmployeeListResponse,
    StaffEmployeeOut,
    StaffEmployeeStatusUpdate,
)
from app.schemas import Employee, Store

router = APIRouter(
    prefix="/staff/store/staff",
    tags=["staff-store-staff"],
    dependencies=[Depends(require_role("store_manager"))],
)


def _default_store_id(db: Session) -> int | None:
    store = db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))
    return store.id if store else None


def _resolve_store_id(
    db: Session, principal: TokenPrincipal, store_id: int | None
) -> int | None:
    return principal.store_id or store_id or _default_store_id(db)


def _find_employee(db: Session, employee_ref: str) -> Employee | None:
    ref = employee_ref.strip()
    # Staff UI may show E-123 while DB stores ST-123 or E-123
    candidates = [ref]
    if ref.upper().startswith("E-") and ref[2:].isdigit():
        candidates.append(f"ST-{ref[2:]}")
        candidates.append(ref[2:])
    if ref.upper().startswith("ST-") and ref[3:].isdigit():
        candidates.append(f"E-{ref[3:]}")
    for code in candidates:
        row = db.scalar(select(Employee).where(Employee.employee_code == code))
        if row:
            return row
    numeric = ref[2:] if ref.upper().startswith("E-") else ref[3:] if ref.upper().startswith("ST-") else ref
    if numeric.isdigit():
        return db.get(Employee, int(numeric))
    return None


@router.get("", response_model=StaffEmployeeListResponse)
def list_store_staff(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffEmployeeListResponse:
    limit, offset = page
    sid = _resolve_store_id(db, principal, None)
    if sid is None:
        return StaffEmployeeListResponse(items=[], total=0, limit=limit, offset=offset)

    stmt = (
        select(Employee)
        .options(*employee_eager())
        .where(Employee.store_id == sid)
    )
    count_stmt = (
        select(func.count())
        .select_from(Employee)
        .where(Employee.store_id == sid)
    )

    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Employee.name.ilike(q),
                Employee.employee_code.ilike(q),
                Employee.job_role.ilike(q),
                Employee.phone.ilike(q),
            )
        )
        count_stmt = count_stmt.where(
            or_(
                Employee.name.ilike(q),
                Employee.employee_code.ilike(q),
                Employee.job_role.ilike(q),
                Employee.phone.ilike(q),
            )
        )

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Employee.employee_code.asc()).limit(limit).offset(offset)
    ).all()
    return StaffEmployeeListResponse(
        items=[StaffEmployeeOut(**staff_employee_row(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffEmployeeOut, status_code=status.HTTP_201_CREATED)
def create_store_employee(
    body: StaffEmployeeCreate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffEmployeeOut:
    sid = _resolve_store_id(db, principal, body.store_id)
    if sid is None:
        raise HTTPException(status_code=400, detail="No store configured")

    name = body.name.strip()
    role = body.role.strip()
    if not name or not role:
        raise HTTPException(status_code=422, detail="Name and role are required")

    code = (body.employee_code or "").strip() or None
    if not code:
        last = db.scalar(select(func.max(Employee.id))) or 0
        code = f"E-{last + 300}"
    if db.scalar(select(Employee.id).where(Employee.employee_code == code)):
        raise HTTPException(status_code=400, detail="employee_code already exists")

    phone = None
    if body.phone:
        phone = "".join(ch for ch in body.phone if ch.isdigit()) or body.phone.strip()

    st = parse_status(body.status) or "active"
    row = Employee(
        employee_code=code,
        name=name,
        job_role=role[:40],
        store_id=sid,
        warehouse_id=None,
        phone=phone,
        shift=(body.shift or "Day")[:20],
        status=st,
        mtd_sales=0,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    row = db.scalar(
        select(Employee).options(*employee_eager()).where(Employee.id == row.id)
    )
    return StaffEmployeeOut(**staff_employee_row(row))


@router.patch("/{employee_ref}/status", response_model=StaffEmployeeOut)
def patch_employee_status(
    employee_ref: str,
    body: StaffEmployeeStatusUpdate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffEmployeeOut:
    row = _find_employee(db, employee_ref)
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found")

    sid = _resolve_store_id(db, principal, None)
    if sid is not None and row.store_id not in (None, sid):
        raise HTTPException(status_code=403, detail="Employee is not at this store")

    parsed = parse_status(body.status)
    if not parsed:
        raise HTTPException(status_code=400, detail="Status must be Active or Inactive")
    row.status = parsed
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(Employee).options(*employee_eager()).where(Employee.id == row.id)
    )
    return StaffEmployeeOut(**staff_employee_row(row))
