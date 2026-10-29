"""Warehouse worklist for store-placed (on-behalf) orders — /staff/warehouse/store-orders.

Store managers place orders for customers that must ship from the warehouse, not
the store shelf. Those orders (order_number ``SA-…``) reserve warehouse stock but
were invisible to the warehouse. This router surfaces them as a plain worklist and
lets the warehouse mark one **Dispatched**.

Deliberately isolated from the web Order / DispatchOrder / Shiprocket pipeline — it
only reads and advances StoreOrder rows, so courier automation is untouched. Stock
is settled by the existing reservation flow (consumed when the store marks the order
collected/delivered), so dispatching here changes no inventory.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import require_role, TokenPrincipal
from app.schemas import ProductVariant, Store, StoreOrder, StoreOrderItem

router = APIRouter(
    prefix="/staff/warehouse/store-orders",
    tags=["staff-warehouse-store-orders"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)

# Store orders still awaiting warehouse dispatch (open, not yet sent).
TODO_STATUSES = ("Pending", "Preparing", "Ready", "Processing", "Ordered")
CLOSED_STATUSES = ("Collected", "Delivered", "Completed", "Cancelled", "Missed", "Void")


class StoreOrderLineOut(BaseModel):
    sku: str
    product: str
    qty: int


class WarehouseStoreOrderOut(BaseModel):
    id: str
    fulfillment: str  # "home_delivery" | "store_pickup"
    destination: str
    address: str
    customer: str
    phone: str
    status: str
    dispatched: bool
    items: int
    qty: int
    created: str | None = None
    lines: list[StoreOrderLineOut]


class WarehouseStoreOrderListResponse(BaseModel):
    items: list[WarehouseStoreOrderOut]


def _eager():
    return (
        selectinload(StoreOrder.items)
        .selectinload(StoreOrderItem.variant)
        .selectinload(ProductVariant.product),
        selectinload(StoreOrder.store),
    )


def _to_out(o: StoreOrder) -> WarehouseStoreOrderOut:
    items = o.items or []
    pickup = (o.channel or "") == "click_collect"
    store_name = o.store.name if o.store else ""
    lines = [
        StoreOrderLineOut(
            sku=(it.variant.sku if it.variant else "") or "",
            product=(
                (it.variant.product.name if it.variant and it.variant.product else None)
                or (it.variant.sku if it.variant else None)
                or "Item"
            ),
            qty=int(it.qty or 1),
        )
        for it in items
    ]
    return WarehouseStoreOrderOut(
        id=o.order_number,
        fulfillment="store_pickup" if pickup else "home_delivery",
        destination=(f"Pickup · {store_name}" if pickup else "Home delivery"),
        address="" if pickup else (o.delivery_address or ""),
        customer=o.customer_name or "",
        phone=o.customer_phone or "",
        status=o.status,
        dispatched=(o.status or "") == "Dispatched",
        items=len(items),
        qty=sum(int(i.qty or 1) for i in items),
        created=o.created_at.isoformat() if o.created_at else None,
        lines=lines,
    )


def _base_query():
    # Only store-placed orders (SA-…) ship from the warehouse; POS/web mirrors don't.
    return (
        select(StoreOrder)
        .options(*_eager())
        .where(StoreOrder.order_number.like("SA-%"))
        .order_by(StoreOrder.id.desc())
    )


@router.get("", response_model=WarehouseStoreOrderListResponse)
def list_store_orders(
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("warehouse_manager")),
    scope: str = Query("todo", pattern="^(todo|all)$"),
) -> WarehouseStoreOrderListResponse:
    stmt = _base_query()
    if scope == "todo":
        stmt = stmt.where(StoreOrder.status.in_(TODO_STATUSES))
    rows = db.scalars(stmt.limit(200)).all()
    return WarehouseStoreOrderListResponse(items=[_to_out(o) for o in rows])


@router.patch("/{order_ref}/dispatch", response_model=WarehouseStoreOrderOut)
def dispatch_store_order(
    order_ref: str,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("warehouse_manager")),
) -> WarehouseStoreOrderOut:
    stmt = _base_query().limit(1)
    order = db.scalar(stmt.where(StoreOrder.order_number == order_ref))
    if order is None:
        raise HTTPException(status_code=404, detail="Store order not found")
    current = order.status or ""
    if current in CLOSED_STATUSES:
        raise HTTPException(status_code=409, detail="This order is already closed.")
    if current == "Dispatched":
        raise HTTPException(status_code=409, detail="This order is already dispatched.")

    # Status flag only — reserved stock stays held until the store marks the
    # order collected/delivered, which consumes it. No courier/Shiprocket call.
    order.status = "Dispatched"
    db.commit()

    refreshed = db.scalar(_base_query().where(StoreOrder.id == order.id).limit(1))
    assert refreshed
    return _to_out(refreshed)
