"""Staff store orders — /staff/store/orders."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.store_orders import (
    CLICK_COLLECT_CANONICAL,
    CLICK_COLLECT_TRANSITIONS,
    list_store_orders_query,
    staff_order_row,
    store_order_eager,
)
from app.database import get_db
from app.deps import pagination, require_role, TokenPrincipal
from app.dto.store_order_dto import (
    StaffStoreOrderListResponse,
    StaffStoreOrderOut,
    StaffStoreOrderStatusPatch,
)
from app.schemas import Store, StoreOrder
from sqlalchemy import select

router = APIRouter(prefix="/staff/store/orders", tags=["staff-store-orders"], dependencies=[Depends(require_role("store_manager"))])

# Stores never fulfill home delivery — that's the warehouse's job.
STORE_VISIBLE_CHANNELS = ("in_store", "click_collect")


def _default_store(db: Session) -> Store | None:
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


def _load_order(db: Session, order_ref: str) -> StoreOrder | None:
    stmt = select(StoreOrder).options(*store_order_eager())
    order = db.scalar(stmt.where(StoreOrder.order_number == order_ref))
    if not order and order_ref.isdigit():
        order = db.scalar(stmt.where(StoreOrder.id == int(order_ref)))
    return order


@router.get("", response_model=StaffStoreOrderListResponse)
def list_orders(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    store_id: int | None = None,
    status_filter: str | None = Query(None, alias="status"),
    channel: str | None = None,
    search: str | None = Query(None, alias="q"),
) -> StaffStoreOrderListResponse:
    limit, offset = page
    sid = principal.store_id or store_id
    if sid is None:
        store = _default_store(db)
        sid = store.id if store else None

    stmt, count_stmt = list_store_orders_query(
        store_id=sid,
        status=None,
        channel=channel,
        search=search,
    )
    stmt = stmt.where(StoreOrder.channel.in_(STORE_VISIBLE_CHANNELS))
    count_stmt = count_stmt.where(StoreOrder.channel.in_(STORE_VISIBLE_CHANNELS))
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
    _: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffStoreOrderOut:
    order = _load_order(db, order_ref)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.channel not in STORE_VISIBLE_CHANNELS:
        raise HTTPException(status_code=404, detail="Order not found")
    return StaffStoreOrderOut(**staff_order_row(order))


@router.patch("/{order_ref}/status", response_model=StaffStoreOrderOut)
def patch_status(
    order_ref: str,
    body: StaffStoreOrderStatusPatch,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffStoreOrderOut:
    order = _load_order(db, order_ref)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.channel != "click_collect":
        raise HTTPException(
            status_code=400,
            detail="Only click & collect orders can be transitioned from the store portal.",
        )

    current = (order.status or "").lower()
    target = body.status.strip().lower()

    if target not in CLICK_COLLECT_CANONICAL:
        raise HTTPException(status_code=400, detail=f"Unknown status: {body.status}")

    allowed = CLICK_COLLECT_TRANSITIONS.get(current, set())
    if target not in allowed and current != target:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move click & collect order from '{order.status}' to '{body.status}'.",
        )

    order.status = CLICK_COLLECT_CANONICAL[target]
    db.commit()
    db.refresh(order)
    return StaffStoreOrderOut(**staff_order_row(order))
