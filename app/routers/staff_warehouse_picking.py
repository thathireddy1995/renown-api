"""Staff warehouse picking — /staff/warehouse/picking."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination
from app.dto.staff_dto import (
    StaffPickListOut,
    StaffPickListPatch,
    StaffPickListResponse,
)
from app.schemas import PickList, PickListItem, User

router = APIRouter(prefix="/staff/warehouse/picking", tags=["staff-warehouse-picking"])


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
        pick.status = body.status

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
