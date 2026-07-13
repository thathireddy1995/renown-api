"""Staff warehouse packing — /staff/warehouse/packing."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_warehouse_staff, pagination
from app.dto.staff_dto import (
    StaffPackCreate,
    StaffPackListResponse,
    StaffPackOut,
)
from app.schemas import DispatchOrder, Pack, User

router = APIRouter(prefix="/staff/warehouse/packing", tags=["staff-warehouse-packing"])


def _pack_out(p: Pack) -> StaffPackOut:
    do = p.dispatch_order.do_number if p.dispatch_order else ""
    weight = "—"
    if p.weight is not None:
        weight = f"{float(p.weight):.1f} kg"
    return StaffPackOut(
        id=p.pack_number,
        do=do,
        packer=p.packer_name or "—",
        boxes=p.boxes or 0,
        weight=weight,
        status=p.status,
    )


@router.get("", response_model=StaffPackListResponse)
def list_packs(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffPackListResponse:
    limit, offset = page
    stmt = select(Pack).options(selectinload(Pack.dispatch_order))
    count_stmt = select(func.count()).select_from(Pack)

    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.outerjoin(
            DispatchOrder, DispatchOrder.id == Pack.dispatch_order_id
        )
        count_stmt = count_stmt.outerjoin(
            DispatchOrder, DispatchOrder.id == Pack.dispatch_order_id
        )
        filt = or_(
            Pack.pack_number.ilike(like),
            Pack.packer_name.ilike(like),
            DispatchOrder.do_number.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Pack.id.desc()).limit(limit).offset(offset)).all()
    return StaffPackListResponse(
        items=[_pack_out(p) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffPackOut, status_code=status.HTTP_201_CREATED)
def create_pack(
    body: StaffPackCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_warehouse_staff),
) -> StaffPackOut:
    dispatch_id = body.dispatch_order_id
    if dispatch_id is None and body.do_number:
        do = db.scalar(
            select(DispatchOrder).where(DispatchOrder.do_number == body.do_number)
        )
        if not do:
            raise HTTPException(status_code=404, detail="Dispatch order not found")
        dispatch_id = do.id
    elif dispatch_id is not None and not db.get(DispatchOrder, dispatch_id):
        raise HTTPException(status_code=404, detail="Dispatch order not found")

    pack_number = f"PK-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(Pack.id).where(Pack.pack_number == pack_number)):
        pack_number = f"PK-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    pack = Pack(
        pack_number=pack_number,
        dispatch_order_id=dispatch_id,
        packer_name=body.packer_name,
        boxes=body.boxes,
        weight=Decimal(str(body.weight)) if body.weight is not None else None,
        status=body.status or "Processing",
    )
    db.add(pack)
    db.commit()
    loaded = db.scalar(
        select(Pack)
        .where(Pack.id == pack.id)
        .options(selectinload(Pack.dispatch_order))
    )
    assert loaded
    return _pack_out(loaded)
