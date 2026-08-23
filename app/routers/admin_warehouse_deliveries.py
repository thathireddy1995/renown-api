"""Admin warehouse online deliveries — /admin/warehouse/deliveries."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.warehouse_deliveries import (
    dispatch_history_row,
    fulfill_online_order,
    list_pending_deliveries_query,
    pending_delivery_row,
    resolve_order,
)
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminDeliveryFulfill,
    AdminDeliveryListResponse,
    AdminDeliveryOut,
    AdminDispatchHistoryListResponse,
    AdminDispatchHistoryOut,
)
from app.schemas import DispatchOrder, Order, Warehouse

router = APIRouter(
    prefix="/admin/warehouse/deliveries",
    tags=["admin-warehouse-deliveries"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("", response_model=AdminDeliveryListResponse)
def list_pending_deliveries(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> AdminDeliveryListResponse:
    limit, offset = page
    stmt, count_stmt = list_pending_deliveries_query(search=search)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Order.id.desc()).limit(limit).offset(offset)
    ).all()
    return AdminDeliveryListResponse(
        items=[AdminDeliveryOut.model_validate(pending_delivery_row(o)) for o in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/history", response_model=AdminDispatchHistoryListResponse)
def list_dispatch_history(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    warehouse_id: int | None = None,
) -> AdminDispatchHistoryListResponse:
    limit, offset = page
    stmt = (
        select(DispatchOrder)
        .options(selectinload(DispatchOrder.items), selectinload(DispatchOrder.order))
        .where(DispatchOrder.destination_type == "d2c")
    )
    count_stmt = (
        select(func.count())
        .select_from(DispatchOrder)
        .where(DispatchOrder.destination_type == "d2c")
    )
    if warehouse_id is not None:
        stmt = stmt.where(DispatchOrder.warehouse_id == warehouse_id)
        count_stmt = count_stmt.where(DispatchOrder.warehouse_id == warehouse_id)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(DispatchOrder.id.desc()).limit(limit).offset(offset)
    ).all()
    return AdminDispatchHistoryListResponse(
        items=[AdminDispatchHistoryOut.model_validate(dispatch_history_row(d)) for d in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AdminDispatchHistoryOut, status_code=status.HTTP_201_CREATED)
def fulfill_delivery(
    body: AdminDeliveryFulfill, db: Session = Depends(get_db)
) -> AdminDispatchHistoryOut:
    if not db.get(Warehouse, body.warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")
    order = resolve_order(db, body.order_ref)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    dispatch = fulfill_online_order(
        db,
        warehouse_id=body.warehouse_id,
        order=order,
        carrier=body.carrier,
        awb=body.awb,
        mark_shipped=body.mark_shipped,
    )
    return AdminDispatchHistoryOut.model_validate(dispatch_history_row(dispatch))
