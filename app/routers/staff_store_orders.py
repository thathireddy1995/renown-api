"""Staff store orders — /staff/store/orders."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.store_orders import list_store_orders_query, staff_order_row, store_order_eager
from app.database import get_db
from app.deps import get_current_store_staff, pagination
from app.dto.store_order_dto import StaffStoreOrderListResponse, StaffStoreOrderOut
from app.schemas import Store, StoreOrder, User
from sqlalchemy import select

router = APIRouter(prefix="/staff/store/orders", tags=["staff-store-orders"])


def _default_store(db: Session) -> Store | None:
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


@router.get("", response_model=StaffStoreOrderListResponse)
def list_orders(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_store_staff),
    page: tuple[int, int] = Depends(pagination),
    store_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    channel: str | None = None,
    search: str | None = Query(None, alias="q"),
) -> StaffStoreOrderListResponse:
    limit, offset = page
    sid = store_id
    if sid is None:
        store = _default_store(db)
        sid = store.id if store else None

    stmt, count_stmt = list_store_orders_query(
        store_id=sid,
        status=None,
        channel=channel,
        search=search,
    )
    if status_filter:
        reverse = {
            "Paid": ["Completed"],
            "Processing": ["Preparing", "Ready", "Processing"],
            "Pending": ["Pending"],
            "Delivered": ["Collected", "Delivered"],
            "Cancelled": ["Void", "Missed", "Cancelled", "Refund pending"],
        }
        mapped = reverse.get(status_filter)
        if mapped:
            stmt = stmt.where(StoreOrder.status.in_(mapped))
            count_stmt = count_stmt.where(StoreOrder.status.in_(mapped))
        else:
            stmt = stmt.where(StoreOrder.status == status_filter)
            count_stmt = count_stmt.where(StoreOrder.status == status_filter)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(StoreOrder.id.desc()).limit(limit).offset(offset)
    ).all()
    return StaffStoreOrderListResponse(
        items=[StaffStoreOrderOut(**staff_order_row(o)) for o in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_ref}", response_model=StaffStoreOrderOut)
def get_order(
    order_ref: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_store_staff),
) -> StaffStoreOrderOut:
    stmt = select(StoreOrder).options(*store_order_eager())
    order = db.scalar(stmt.where(StoreOrder.order_number == order_ref))
    if not order and order_ref.isdigit():
        order = db.scalar(stmt.where(StoreOrder.id == int(order_ref)))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return StaffStoreOrderOut(**staff_order_row(order))
