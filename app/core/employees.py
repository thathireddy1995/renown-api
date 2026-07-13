"""Employee list serializers and status helpers."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import joinedload

from app.schemas import Employee


def format_inr(amount: Decimal | float | int | None) -> str:
    if amount is None:
        return "—"
    n = int(round(float(amount)))
    if n == 0:
        return "—"
    s = str(abs(n))
    if len(s) <= 3:
        body = s
    else:
        body = s[-3:]
        s = s[:-3]
        while s:
            body = s[-2:] + "," + body
            s = s[:-2]
    return f"₹{body}"


def admin_status(raw: str) -> str:
    return "On duty" if raw == "active" else "Off"


def staff_status(raw: str) -> str:
    return "Active" if raw == "active" else "Inactive"


def parse_status(label: str | None) -> str | None:
    if label is None:
        return None
    key = label.strip().lower()
    if key in {"active", "on duty", "on_duty"}:
        return "active"
    if key in {"inactive", "off"}:
        return "inactive"
    return key if key in {"active", "inactive"} else None


def employee_eager():
    return (joinedload(Employee.store), joinedload(Employee.warehouse))


def admin_employee_row(row: Employee) -> dict:
    if row.store_id:
        emp_type = "store"
        location = row.store.name if row.store else ""
    else:
        emp_type = "warehouse"
        location = row.warehouse.name if row.warehouse else ""
    return {
        "id": row.employee_code,
        "name": row.name,
        "role": row.job_role,
        "type": emp_type,
        "location": location,
        "shift": row.shift or "Day",
        "status": admin_status(row.status),
    }


def staff_employee_row(row: Employee) -> dict:
    code = row.employee_code
    if code.startswith("ST-") and code[3:].isdigit():
        display_id = f"E-{code[3:]}"
    else:
        display_id = code
    return {
        "id": display_id,
        "name": row.name,
        "role": row.job_role,
        "phone": row.phone or "—",
        "shift": row.shift or "—",
        "sales": format_inr(row.mtd_sales),
        "status": staff_status(row.status),
    }
