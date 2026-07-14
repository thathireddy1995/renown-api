"""Staff warehouse picking — /staff/warehouse/picking."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination, require_role
from app.dto.staff_dto import (
    StaffPickListCreate,
    StaffPickListOut,
    StaffPickListPatch,
    StaffPickListResponse,
)
from app.schemas import PickList, PickListItem, ProductVariant, User, Warehouse

router = APIRouter(
    prefix="/staff/warehouse/picking",
    tags=["staff-warehouse-picking"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


def _default_warehouse(db: Session) -> Warehouse | None:
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def _pick_out(p: PickList) -> StaffPickListOut:
    items = p.items or []
    total = sum(i.qty for i in items)
    picked = sum(i.picked_qty for i in items)
    return StaffPickListOut(
        id=p.list_number,
        wave=p.wave_number,
        picker=p.picker_name or "—",
        items=total,
        progress=f"{picked}/{total}",
        status=p.status,
    )


@router.get("", response_model=StaffPickListResponse)
def list_pick_lists(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffPickListResponse:
    limit, offset = page
    stmt = select(PickList).options(selectinload(PickList.items))
    count_stmt = select(func.count()).select_from(PickList)

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            PickList.list_number.ilike(like),
            PickList.wave_number.ilike(like),
            PickList.picker_name.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(PickList.id.desc()).limit(limit).offset(offset)
    ).all()
    return StaffPickListResponse(
        items=[_pick_out(p) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffPickListOut, status_code=status.HTTP_201_CREATED)
def release_wave(
    body: StaffPickListCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffPickListOut:
    warehouse_id = body.warehouse_id
    if warehouse_id is None:
        wh = _default_warehouse(db)
        if not wh:
            raise HTTPException(status_code=400, detail="No warehouse configured")
        warehouse_id = wh.id
    elif not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")

    ts = int(datetime.now(timezone.utc).timestamp()) % 100000
    list_number = f"PL-{ts}"
    while db.scalar(select(PickList.id).where(PickList.list_number == list_number)):
        ts += 1
        list_number = f"PL-{ts}"

    wave = (body.wave or "").strip() or f"Wave {datetime.now(timezone.utc).strftime('%H:%M')}"
    status_val = (body.status or "Pending").strip().title()
    if status_val not in ("Pending", "Processing", "Done", "Cancelled"):
        status_val = "Pending"

    pick = PickList(
        list_number=list_number,
        wave_number=wave,
        warehouse_id=warehouse_id,
        picker_name=(body.picker or "").strip() or None,
        status=status_val,
    )
    db.add(pick)
    db.flush()

    variants = db.scalars(
        select(ProductVariant).order_by(ProductVariant.id.asc()).limit(max(1, min(body.items, 20)))
    ).all()
    if variants:
        per = max(1, body.items // len(variants))
        rem = body.items - per * len(variants)
        for i, variant in enumerate(variants):
            qty = per + (1 if i < rem else 0)
            if qty <= 0:
                continue
            db.add(
                PickListItem(
                    pick_list_id=pick.id,
                    variant_id=variant.id,
                    qty=qty,
                    picked_qty=0,
                )
            )

    db.commit()
    loaded = db.scalar(
        select(PickList)
        .where(PickList.id == pick.id)
        .options(selectinload(PickList.items))
    )
    assert loaded
    return _pick_out(loaded)


def _resolve_pick(db: Session, pick_ref: str) -> PickList | None:
    stmt = select(PickList).options(selectinload(PickList.items))
    row = db.scalar(stmt.where(PickList.list_number == pick_ref))
    if row:
        return row
    if pick_ref.isdigit():
        return db.scalar(stmt.where(PickList.id == int(pick_ref)))
    return None


@router.patch("/{pick_ref}", response_model=StaffPickListOut)
def update_pick_list(
    pick_ref: str,
    body: StaffPickListPatch,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffPickListOut:
    pick = _resolve_pick(db, pick_ref)
    if not pick:
        raise HTTPException(status_code=404, detail="Pick list not found")

    if body.picker is not None:
        pick.picker_name = body.picker
    if body.status is not None:
        raw = body.status.strip().title()
        if raw not in ("Pending", "Processing", "Done", "Cancelled"):
            raise HTTPException(status_code=400, detail="Invalid status")
        pick.status = raw

    by_id = {i.id: i for i in (pick.items or [])}
    for patch in body.items:
        item = by_id.get(patch.item_id)
        if not item:
            raise HTTPException(
                status_code=404, detail=f"Pick item {patch.item_id} not found"
            )
        item.picked_qty = max(0, patch.picked_qty)

    if body.status is None and pick.items:
        total = sum(i.qty for i in pick.items)
        picked = sum(i.picked_qty for i in pick.items)
        if total > 0 and picked >= total:
            pick.status = "Done"
        elif picked > 0:
            pick.status = "Processing"

    db.commit()
    refreshed = _resolve_pick(db, pick_ref)
    assert refreshed
    return _pick_out(refreshed)
