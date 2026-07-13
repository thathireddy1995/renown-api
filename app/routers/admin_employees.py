"""Admin employees — /admin/employees."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.core.employees import (
    admin_employee_row,
    employee_eager,
    parse_status,
)
from app.database import get_db
from app.deps import pagination
from app.dto.employee_dto import (
    AdminEmployeeCreate,
    AdminEmployeeListResponse,
    AdminEmployeeOut,
    AdminEmployeeUpdate,
)
from app.schemas import Employee, Store, Warehouse

router = APIRouter(
    prefix="/admin/employees",
    tags=["admin-employees"],
    dependencies=[Depends(require_role("admin"))],
)


def _resolve_location(
    db: Session,
    emp_type: str | None,
    location: str | None,
    store_id: int | None,
    warehouse_id: int | None,
) -> tuple[int | None, int | None]:
    if store_id is not None:
        return store_id, None
    if warehouse_id is not None:
        return None, warehouse_id
    if location:
        if emp_type == "warehouse" or (emp_type is None and warehouse_id is None):
            wh = db.scalar(select(Warehouse).where(Warehouse.name == location))
            if wh:
                return None, wh.id
        store = db.scalar(select(Store).where(Store.name == location))
        if store:
            return store.id, None
        wh = db.scalar(select(Warehouse).where(Warehouse.name == location))
        if wh:
            return None, wh.id
    return store_id, warehouse_id


@router.get("", response_model=AdminEmployeeListResponse)
def list_employees(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
    role: str | None = None,
    type_filter: str | None = Query(None, alias="type"),
) -> AdminEmployeeListResponse:
    limit, offset = page
    stmt = select(Employee).options(*employee_eager())
    count_stmt = select(func.count()).select_from(Employee)

    if type_filter == "store":
        stmt = stmt.where(Employee.store_id.is_not(None))
        count_stmt = count_stmt.where(Employee.store_id.is_not(None))
    elif type_filter == "warehouse":
        stmt = stmt.where(Employee.warehouse_id.is_not(None))
        count_stmt = count_stmt.where(Employee.warehouse_id.is_not(None))

    if role:
        stmt = stmt.where(Employee.job_role.ilike(role))
        count_stmt = count_stmt.where(Employee.job_role.ilike(role))

    if search:
        q = f"%{search.strip()}%"
        stmt = (
            stmt.outerjoin(Store, Employee.store_id == Store.id)
            .outerjoin(Warehouse, Employee.warehouse_id == Warehouse.id)
            .where(
                or_(
                    Employee.name.ilike(q),
                    Employee.employee_code.ilike(q),
                    Employee.job_role.ilike(q),
                    Store.name.ilike(q),
                    Warehouse.name.ilike(q),
                )
            )
        )
        count_stmt = (
            select(func.count())
            .select_from(Employee)
            .outerjoin(Store, Employee.store_id == Store.id)
            .outerjoin(Warehouse, Employee.warehouse_id == Warehouse.id)
            .where(
                or_(
                    Employee.name.ilike(q),
                    Employee.employee_code.ilike(q),
                    Employee.job_role.ilike(q),
                    Store.name.ilike(q),
                    Warehouse.name.ilike(q),
                )
            )
        )
        if type_filter == "store":
            count_stmt = count_stmt.where(Employee.store_id.is_not(None))
        elif type_filter == "warehouse":
            count_stmt = count_stmt.where(Employee.warehouse_id.is_not(None))

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Employee.employee_code.asc()).limit(limit).offset(offset)
    ).all()
    return AdminEmployeeListResponse(
        items=[AdminEmployeeOut(**admin_employee_row(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AdminEmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: AdminEmployeeCreate,
    db: Session = Depends(get_db),
) -> AdminEmployeeOut:
    store_id, warehouse_id = _resolve_location(
        db, body.type, body.location, body.store_id, body.warehouse_id
    )
    if body.type == "store" and not store_id:
        raise HTTPException(status_code=400, detail="store_id or location required")
    if body.type == "warehouse" and not warehouse_id:
        raise HTTPException(status_code=400, detail="warehouse_id or location required")

    code = body.employee_code
    if not code:
        last = db.scalar(select(func.max(Employee.id))) or 0
        code = f"E-{last + 300}"

    if db.scalar(select(Employee.id).where(Employee.employee_code == code)):
        raise HTTPException(status_code=400, detail="employee_code already exists")

    st = parse_status(body.status) or "active"
    row = Employee(
        employee_code=code,
        name=body.name,
        job_role=body.role[:40],
        store_id=store_id if body.type == "store" else None,
        warehouse_id=warehouse_id if body.type == "warehouse" else None,
        phone=body.phone,
        shift=(body.shift or "Day")[:20],
        status=st,
        mtd_sales=body.mtd_sales,
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
    return AdminEmployeeOut(**admin_employee_row(row))


@router.get("/{employee_ref}", response_model=AdminEmployeeOut)
def get_employee(employee_ref: str, db: Session = Depends(get_db)) -> AdminEmployeeOut:
    row = db.scalar(
        select(Employee)
        .options(*employee_eager())
        .where(Employee.employee_code == employee_ref)
    )
    if not row and employee_ref.isdigit():
        row = db.scalar(
            select(Employee)
            .options(*employee_eager())
            .where(Employee.id == int(employee_ref))
        )
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found")
    return AdminEmployeeOut(**admin_employee_row(row))


@router.patch("/{employee_ref}", response_model=AdminEmployeeOut)
def update_employee(
    employee_ref: str,
    body: AdminEmployeeUpdate,
    db: Session = Depends(get_db),
) -> AdminEmployeeOut:
    row = db.scalar(select(Employee).where(Employee.employee_code == employee_ref))
    if not row and employee_ref.isdigit():
        row = db.get(Employee, int(employee_ref))
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found")

    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        row.name = data["name"]
    if "role" in data and data["role"] is not None:
        row.job_role = data["role"][:40]
    if "shift" in data and data["shift"] is not None:
        row.shift = data["shift"][:20]
    if "phone" in data:
        row.phone = data["phone"]
    if "mtd_sales" in data and data["mtd_sales"] is not None:
        row.mtd_sales = data["mtd_sales"]
    if "status" in data and data["status"] is not None:
        parsed = parse_status(data["status"])
        if parsed:
            row.status = parsed

    emp_type = data.get("type")
    if emp_type or "location" in data or "store_id" in data or "warehouse_id" in data:
        sid, wid = _resolve_location(
            db,
            emp_type or ("store" if row.store_id else "warehouse"),
            data.get("location"),
            data.get("store_id", row.store_id),
            data.get("warehouse_id", row.warehouse_id),
        )
        if (emp_type or ("store" if row.store_id else "warehouse")) == "store":
            row.store_id = sid
            row.warehouse_id = None
        else:
            row.warehouse_id = wid
            row.store_id = None

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(Employee).options(*employee_eager()).where(Employee.id == row.id)
    )
    return AdminEmployeeOut(**admin_employee_row(row))


@router.delete("/{employee_ref}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_ref: str, db: Session = Depends(get_db)) -> None:
    row = db.scalar(select(Employee).where(Employee.employee_code == employee_ref))
    if not row and employee_ref.isdigit():
        row = db.get(Employee, int(employee_ref))
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
