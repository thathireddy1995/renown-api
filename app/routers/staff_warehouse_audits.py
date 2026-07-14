"""Staff warehouse cycle audits."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.deps import TokenPrincipal, require_role
from app.database import get_db
from app.deps import pagination
from app.dto.operations_dto import (
    AuditCreate,
    AuditItemCountIn,
    AuditListResponse,
    AuditOut,
    AuditStatusUpdate,
)
from app.schemas import (
    InventoryAudit,
    InventoryAuditItem,
    Warehouse,
    WarehouseInventory,
)

router = APIRouter(
    prefix="/staff/warehouse/audits",
    tags=["staff-warehouse-audits"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)

STATUS_UI = {
    "scheduled": "Pending",
    "in_progress": "In progress",
    "completed": "Done",
}

STATUS_DB = {
    "pending": "scheduled",
    "scheduled": "scheduled",
    "in progress": "in_progress",
    "in_progress": "in_progress",
    "processing": "in_progress",
    "done": "completed",
    "completed": "completed",
}


def _normalize_status(raw: str | None) -> str:
    key = (raw or "Pending").strip().lower().replace("_", " ")
    if key not in STATUS_DB:
        raise HTTPException(status_code=422, detail=f"Unknown status: {raw}")
    return STATUS_DB[key]


def _wh_id(db: Session, principal: TokenPrincipal) -> int | None:
    if principal.warehouse_id is not None:
        return principal.warehouse_id
    wh = db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))
    return wh.id if wh else None


def _date_label(row: InventoryAudit) -> str:
    if row.status == "scheduled" and not row.completed_at:
        return "Scheduled"
    when = row.completed_at or row.created_at
    if when is None:
        return "—"
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc).date()
    d = when.date()
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    return d.isoformat()


def _audit_out(
    row: InventoryAudit,
    *,
    counted_override: int | None = None,
    expected_override: int | None = None,
) -> AuditOut:
    items = row.items or []
    counted = (
        counted_override
        if counted_override is not None
        else sum(i.counted_qty for i in items)
    )
    expected = (
        expected_override
        if expected_override is not None
        else sum(i.expected_qty for i in items)
    )
    variance = counted - expected
    return AuditOut(
        id=row.audit_number,
        zone=row.zone or "—",
        counted=counted,
        expected=expected,
        variance=variance,
        auditor=row.auditor_name or "—",
        date=_date_label(row),
        status=STATUS_UI.get(row.status, row.status),
    )


def _resolve_audit(db: Session, audit_ref: str) -> InventoryAudit | None:
    stmt = select(InventoryAudit).options(selectinload(InventoryAudit.items))
    row = db.scalar(stmt.where(InventoryAudit.audit_number == audit_ref))
    if row:
        return row
    if audit_ref.isdigit():
        return db.scalar(stmt.where(InventoryAudit.id == int(audit_ref)))
    return None


@router.get("", response_model=AuditListResponse)
def list_audits(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> AuditListResponse:
    limit, offset = page
    wid = _wh_id(db, principal)
    stmt = select(InventoryAudit).options(selectinload(InventoryAudit.items))
    count_stmt = select(func.count()).select_from(InventoryAudit)
    if wid is not None:
        stmt = stmt.where(InventoryAudit.warehouse_id == wid)
        count_stmt = count_stmt.where(InventoryAudit.warehouse_id == wid)
    if search:
        q = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                InventoryAudit.audit_number.ilike(q),
                InventoryAudit.zone.ilike(q),
                InventoryAudit.auditor_name.ilike(q),
            )
        )
        count_stmt = count_stmt.where(
            or_(
                InventoryAudit.audit_number.ilike(q),
                InventoryAudit.zone.ilike(q),
                InventoryAudit.auditor_name.ilike(q),
            )
        )
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(InventoryAudit.id.desc()).limit(limit).offset(offset)
    ).all()
    return AuditListResponse(
        items=[_audit_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AuditOut, status_code=status.HTTP_201_CREATED)
def create_audit(
    body: AuditCreate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
) -> AuditOut:
    wid = body.warehouse_id or _wh_id(db, principal)
    if wid is None:
        raise HTTPException(status_code=400, detail="No warehouse configured")

    last = db.scalar(select(func.max(InventoryAudit.id))) or 700
    number = f"AU-{last + 1}"

    # Seed expected qty from warehouse inventory (top variants by on_hand)
    inv_rows = db.execute(
        select(WarehouseInventory.variant_id, WarehouseInventory.on_hand)
        .where(WarehouseInventory.warehouse_id == wid)
        .order_by(WarehouseInventory.on_hand.desc())
        .limit(20)
    ).all()

    audit = InventoryAudit(
        audit_number=number,
        warehouse_id=wid,
        zone=body.zone,
        status=_normalize_status(body.status) if body.status else "scheduled",
        auditor_name=body.auditor_name,
    )
    db.add(audit)
    db.flush()
    for variant_id, on_hand in inv_rows:
        db.add(
            InventoryAuditItem(
                inventory_audit_id=audit.id,
                variant_id=variant_id,
                expected_qty=int(on_hand or 0),
                counted_qty=0,
                variance=0 - int(on_hand or 0),
            )
        )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(InventoryAudit)
        .options(selectinload(InventoryAudit.items))
        .where(InventoryAudit.id == audit.id)
    )
    return _audit_out(
        row,
        counted_override=body.counted,
        expected_override=body.expected,
    )


@router.patch("/{audit_ref}/status", response_model=AuditOut)
def patch_audit_status(
    audit_ref: str,
    body: AuditStatusUpdate,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("warehouse_manager")),
) -> AuditOut:
    audit = _resolve_audit(db, audit_ref)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    new_status = _normalize_status(body.status)
    audit.status = new_status
    if new_status == "completed":
        audit.completed_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = _resolve_audit(db, audit_ref)
    assert refreshed
    return _audit_out(refreshed)


@router.patch("/{audit_ref}/items/{item_id}", response_model=AuditOut)
def patch_item_count(
    audit_ref: str,
    item_id: int,
    body: AuditItemCountIn,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("warehouse_manager")),
) -> AuditOut:
    audit = db.scalar(
        select(InventoryAudit).where(InventoryAudit.audit_number == audit_ref)
    )
    if not audit and audit_ref.isdigit():
        audit = db.get(InventoryAudit, int(audit_ref))
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    # variance computed in SQL
    result = db.execute(
        update(InventoryAuditItem)
        .where(
            InventoryAuditItem.id == item_id,
            InventoryAuditItem.inventory_audit_id == audit.id,
        )
        .values(
            counted_qty=body.counted_qty,
            variance=body.counted_qty - InventoryAuditItem.expected_qty,
        )
        .returning(InventoryAuditItem.id)
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="Audit item not found")

    audit.status = "in_progress"
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    row = db.scalar(
        select(InventoryAudit)
        .options(selectinload(InventoryAudit.items))
        .where(InventoryAudit.id == audit.id)
    )
    return _audit_out(row)
