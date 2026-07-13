"""Staff store directory — /staff/store/staff (read-only)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import TokenPrincipal, require_role
from app.core.employees import employee_eager, staff_employee_row
from app.database import get_db
from app.deps import pagination
from app.dto.employee_dto import StaffEmployeeListResponse, StaffEmployeeOut
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


@router.get("", response_model=StaffEmployeeListResponse)
def list_store_staff(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffEmployeeListResponse:
    limit, offset = page
    sid = principal.store_id or _default_store_id(db)
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
