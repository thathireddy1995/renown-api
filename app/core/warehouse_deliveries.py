"""Online (home-delivery) warehouse fulfillment — short DB transactions only.

Shiprocket HTTP is intentionally not called here. Lambda/RDS stays healthy:
persist the dispatch + deduct stock, then attach an AWB (typed or from
Shiprocket) on a later request.
"""

from __future__ import annotations

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from fastapi import HTTPException

from app.core.admin_order_status import admin_status_label
from app.core.ist import format_ist_datetime, now as ist_now
from app.schemas import (
    DispatchOrder,
    DispatchOrderItem,
    Order,
    OrderItem,
    ProductVariant,
    Warehouse,
    WarehouseInventory,
)

OPEN_ORDER_STATUSES = ("placed", "verified", "packed")
SHIP_MODES = ("ship", "home", "delivery")


def delivery_eager_options():
    return (
        selectinload(Order.items).selectinload(OrderItem.variant),
        selectinload(Order.customer),
        selectinload(Order.address),
    )


def _open_dispatch_exists():
    return exists(
        select(DispatchOrder.id).where(
            DispatchOrder.order_id == Order.id,
            func.lower(DispatchOrder.status) != "cancelled",
        )
    )


def list_pending_deliveries_query(*, search: str | None = None):
    stmt = (
        select(Order)
        .options(*delivery_eager_options())
        .where(
            Order.delivery.in_(SHIP_MODES),
            Order.status.in_(OPEN_ORDER_STATUSES),
            ~_open_dispatch_exists(),
        )
    )
    count_stmt = (
        select(func.count())
        .select_from(Order)
        .where(
            Order.delivery.in_(SHIP_MODES),
            Order.status.in_(OPEN_ORDER_STATUSES),
            ~_open_dispatch_exists(),
        )
    )

    if search and search.strip():
        like = f"%{search.strip()}%"
        from app.schemas import Customer

        stmt = stmt.outerjoin(Customer, Customer.id == Order.customer_id)
        count_stmt = count_stmt.outerjoin(Customer, Customer.id == Order.customer_id)
        filt = or_(
            Order.order_number.ilike(like),
            Customer.name.ilike(like),
            Customer.phone.ilike(like),
            Order.awb_code.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    return stmt, count_stmt


def pending_delivery_row(order: Order) -> dict:
    customer = order.customer
    address = order.address
    items = order.items or []
    qty = sum(int(i.qty or 0) for i in items)
    city = (address.city if address else None) or ""
    return {
        "id": order.order_number,
        "order_id": order.id,
        "customer": (customer.name if customer else None) or f"Customer #{order.customer_id}",
        "phone": (customer.phone if customer else None) or (address.phone if address else None),
        "city": city,
        "address": _address_line(address),
        "items": len(items),
        "qty": qty,
        "total": float(order.total or 0),
        "status": admin_status_label(order.status),
        "date": format_ist_datetime(order.created_at),
    }


def _address_line(address) -> str:
    if address is None:
        return ""
    parts = [
        address.line1,
        address.line2,
        address.city,
        address.state,
        address.postal_code,
    ]
    return ", ".join(p.strip() for p in parts if p and str(p).strip())


def _decrement_warehouse(db: Session, warehouse_id: int, variant_id: int, qty: int) -> None:
    if qty <= 0:
        return
    row = db.scalar(
        select(WarehouseInventory).where(
            WarehouseInventory.warehouse_id == warehouse_id,
            WarehouseInventory.variant_id == variant_id,
        )
    )
    sku = ""
    variant = db.get(ProductVariant, variant_id)
    if variant:
        sku = variant.sku or str(variant_id)
    if not row:
        raise HTTPException(
            status_code=400,
            detail=f"No warehouse stock for SKU {sku or variant_id}",
        )
    if int(row.on_hand or 0) < qty:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient warehouse stock for SKU {sku or variant_id}",
        )
    row.on_hand = int(row.on_hand) - qty


def next_do_number(db: Session) -> str:
    base = int(ist_now().timestamp() * 1000) % 10_000_000
    for step in range(25):
        num = f"DO-{base + step}"
        if not db.scalar(select(DispatchOrder.id).where(DispatchOrder.do_number == num)):
            return num
    raise HTTPException(status_code=500, detail="Could not allocate dispatch number")


def resolve_order(db: Session, order_ref: str) -> Order | None:
    stmt = select(Order).options(*delivery_eager_options())
    row = db.scalar(stmt.where(Order.order_number == order_ref))
    if row:
        return row
    if order_ref.isdigit():
        return db.scalar(stmt.where(Order.id == int(order_ref)))
    return None


def fulfill_online_order(
    db: Session,
    *,
    warehouse_id: int,
    order: Order,
    carrier: str | None = None,
    awb: str | None = None,
    mark_shipped: bool = True,
) -> DispatchOrder:
    if not db.get(Warehouse, warehouse_id):
        raise HTTPException(status_code=404, detail="Warehouse not found")
    if (order.delivery or "ship") == "pickup":
        raise HTTPException(status_code=422, detail="Click & collect orders are fulfilled by the store")
    if (order.status or "").lower() in ("cancelled", "delivered"):
        raise HTTPException(status_code=400, detail="Order cannot be dispatched")

    existing = db.scalar(
        select(DispatchOrder.id).where(
            DispatchOrder.order_id == order.id,
            func.lower(DispatchOrder.status) != "cancelled",
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Order already has an open dispatch")

    lines: list[tuple[int, int]] = []
    for item in order.items or []:
        if not item.variant_id or int(item.qty or 0) <= 0:
            continue
        lines.append((int(item.variant_id), int(item.qty)))
    if not lines:
        raise HTTPException(status_code=400, detail="Order has no fulfillable SKUs")

    for variant_id, qty in lines:
        _decrement_warehouse(db, warehouse_id, variant_id, qty)

    customer = order.customer
    address = order.address
    dest = (customer.name if customer else None) or order.order_number
    if address and address.city:
        dest = f"{dest} · {address.city}"

    dispatch = DispatchOrder(
        do_number=next_do_number(db),
        warehouse_id=warehouse_id,
        order_id=order.id,
        destination_type="d2c",
        destination_id=order.id,
        destination_label=dest,
        carrier=(carrier or "Shiprocket").strip() or "Shiprocket",
        awb=(awb or "").strip() or None,
        status="Processing" if (awb or "").strip() else "Pending",
    )
    db.add(dispatch)
    db.flush()
    for variant_id, qty in lines:
        db.add(
            DispatchOrderItem(
                dispatch_order_id=dispatch.id,
                variant_id=variant_id,
                qty=qty,
            )
        )

    if (awb or "").strip():
        order.awb_code = awb.strip()
    if carrier:
        order.courier_name = carrier.strip() or order.courier_name
    if mark_shipped and (order.status or "").lower() in ("placed", "verified", "packed"):
        order.status = "shipped"
        dispatch.status = "Processing"

    db.commit()
    loaded = db.scalar(
        select(DispatchOrder)
        .where(DispatchOrder.id == dispatch.id)
        .options(selectinload(DispatchOrder.items), selectinload(DispatchOrder.order))
    )
    assert loaded
    return loaded


def dispatch_history_row(d: DispatchOrder) -> dict:
    items = d.items or []
    order = d.order
    return {
        "id": d.do_number,
        "order": order.order_number if order else "",
        "destination": d.destination_label or "",
        "carrier": d.carrier or "",
        "awb": d.awb or "",
        "items": sum(i.qty for i in items),
        "status": d.status,
        "warehouse_id": d.warehouse_id,
        "date": format_ist_datetime(d.created_at),
    }
