"""Admin warehouse online deliveries — /admin/warehouse/deliveries."""

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.shiprocket import (
    ShiprocketError,
    generate_label,
    generate_manifest,
    get_wallet_balance,
    print_invoice,
    print_manifest,
)
from app.core.order_club import club_lead, club_many, unclub_order
from app.core.shiprocket_fulfill import list_couriers_for_order, pickup_postcode
from app.core.warehouse_deliveries import (
    club_search,
    club_search_row,
    clubbed_by_lead,
    delivery_eager_options,
    dispatch_history_row,
    fulfill_online_order,
    list_pending_deliveries_query,
    pending_delivery_row,
    resolve_order,
)
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminClubRequest,
    AdminClubSearchOrderOut,
    AdminClubSearchOut,
    AdminCourierOptionOut,
    AdminCourierOptionsOut,
    AdminDeliveryFulfill,
    AdminDeliveryListResponse,
    AdminDeliveryOut,
    AdminDispatchHistoryListResponse,
    AdminDispatchHistoryOut,
    AdminShiprocketDocOut,
    AdminShiprocketWalletOut,
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
    clubbed = clubbed_by_lead(db, [o.id for o in rows])
    items = [
        AdminDeliveryOut.model_validate(pending_delivery_row(o, clubbed.get(o.id))) for o in rows
    ]
    return AdminDeliveryListResponse(items=items, total=total, limit=limit, offset=offset)


def _pending_row(db: Session, order: Order) -> AdminDeliveryOut:
    refreshed = resolve_order(db, order.order_number) or order
    return AdminDeliveryOut.model_validate(
        pending_delivery_row(refreshed, clubbed_by_lead(db, [refreshed.id]).get(refreshed.id))
    )


@router.get("/club/search", response_model=AdminClubSearchOut)
def search_club_orders(
    phone: str = Query(..., min_length=10, max_length=20), db: Session = Depends(get_db)
) -> AdminClubSearchOut:
    """Open home-delivery orders for a mobile number, to pick which ship together."""
    orders = club_search(db, phone)
    by_id = {o.id: o for o in orders}
    children: dict[int, list[Order]] = {}
    for o in orders:
        if o.clubbed_into_id:
            children.setdefault(o.clubbed_into_id, []).append(o)
    rows = []
    for o in orders:
        lead = by_id.get(o.clubbed_into_id) if o.clubbed_into_id else None
        lead_ref = lead.order_number if lead else (club_lead(db, o).order_number if o.clubbed_into_id else None)
        rows.append(
            AdminClubSearchOrderOut.model_validate(club_search_row(o, children.get(o.id, []), lead_ref))
        )
    return AdminClubSearchOut(phone=phone, items=rows)


@router.post("/club", response_model=AdminDeliveryOut)
def club_deliveries(body: AdminClubRequest, db: Session = Depends(get_db)) -> AdminDeliveryOut:
    """Ship the selected orders in one parcel."""
    orders = []
    for ref in body.order_refs:
        order = resolve_order(db, ref)
        if not order:
            raise HTTPException(status_code=404, detail=f"Order {ref} not found")
        orders.append(order)
    lead = club_many(db, orders)
    db.commit()
    return _pending_row(db, lead)


@router.delete("/{order_ref}/club", response_model=AdminDeliveryOut)
def unclub_delivery(order_ref: str, db: Session = Depends(get_db)) -> AdminDeliveryOut:
    """Take ``order_ref`` out of its parcel so it ships on its own."""
    order = resolve_order(db, order_ref)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    lead = club_lead(db, order)
    unclub_order(db, order)
    db.commit()
    return _pending_row(db, lead or order)


@router.get("/wallet", response_model=AdminShiprocketWalletOut)
def shiprocket_wallet() -> AdminShiprocketWalletOut:
    try:
        balance = get_wallet_balance()
    except (ShiprocketError, requests.RequestException) as err:
        raise HTTPException(status_code=502, detail=f"Shiprocket wallet unavailable: {err}") from err
    return AdminShiprocketWalletOut(balance=balance)


@router.get("/history", response_model=AdminDispatchHistoryListResponse)
def list_dispatch_history(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    warehouse_id: int | None = None,
) -> AdminDispatchHistoryListResponse:
    limit, offset = page
    stmt = (
        select(DispatchOrder)
        .options(
            selectinload(DispatchOrder.items),
            selectinload(DispatchOrder.order).options(*delivery_eager_options()),
        )
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
    clubbed = clubbed_by_lead(db, [d.order_id for d in rows if d.order_id])
    return AdminDispatchHistoryListResponse(
        items=[
            AdminDispatchHistoryOut.model_validate(
                dispatch_history_row(d, clubbed.get(d.order_id))
            )
            for d in rows
        ],
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
        courier_id=body.courier_id,
        mark_shipped=body.mark_shipped,
    )
    clubbed = clubbed_by_lead(db, [order.id]).get(order.id)
    return AdminDispatchHistoryOut.model_validate(dispatch_history_row(dispatch, clubbed))


def _order_for_docs(db: Session, order_ref: str) -> Order:
    order = resolve_order(db, order_ref)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/{order_ref}/couriers", response_model=AdminCourierOptionsOut)
def list_delivery_couriers(
    order_ref: str, db: Session = Depends(get_db)
) -> AdminCourierOptionsOut:
    """Shiprocket serviceability options for warehouse partner selection."""
    order = resolve_order(db, order_ref)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        # Ensure address / items are loaded for pin + COD check.
        loaded = db.scalar(
            select(Order)
            .where(Order.id == order.id)
            .options(*delivery_eager_options())
        )
        order = loaded or order
        rows = list_couriers_for_order(db, order)
    except ShiprocketError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    prepaid = (order.payment_method or "").lower() == "razorpay" and (
        order.payment_status or ""
    ).lower() == "paid"
    delivery = ""
    if order.address and order.address.postal_code:
        delivery = "".join(c for c in order.address.postal_code if c.isdigit())[:6]
    return AdminCourierOptionsOut(
        order_ref=order.order_number,
        pickup_postcode=pickup_postcode(db),
        delivery_postcode=delivery,
        cod=not prepaid,
        items=[AdminCourierOptionOut.model_validate(r) for r in rows],
    )

@router.get("/{order_ref}/label", response_model=AdminShiprocketDocOut)
def download_label(order_ref: str, db: Session = Depends(get_db)) -> AdminShiprocketDocOut:
    order = _order_for_docs(db, order_ref)
    sid = (order.shiprocket_shipment_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="No Shiprocket shipment on this order")
    try:
        res = generate_label([sid])
    except ShiprocketError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    url = res.get("label_url") or ""
    return AdminShiprocketDocOut(
        kind="label",
        url=url,
        message="OK" if url else "Label requested — URL missing in Shiprocket response",
    )


@router.get("/{order_ref}/manifest", response_model=AdminShiprocketDocOut)
def download_manifest(order_ref: str, db: Session = Depends(get_db)) -> AdminShiprocketDocOut:
    order = _order_for_docs(db, order_ref)
    sid = (order.shiprocket_shipment_id or "").strip()
    if not sid:
        raise HTTPException(status_code=400, detail="No Shiprocket shipment on this order")
    try:
        generate_manifest([sid])
        res = print_manifest(shipment_ids=[sid])
        if not res.get("manifest_url") and order.shiprocket_order_id:
            res = print_manifest(order_ids=[order.shiprocket_order_id])
    except ShiprocketError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    url = res.get("manifest_url") or ""
    return AdminShiprocketDocOut(
        kind="manifest",
        url=url,
        message="OK" if url else "Manifest requested — URL missing in Shiprocket response",
    )


@router.get("/{order_ref}/invoice", response_model=AdminShiprocketDocOut)
def download_invoice(order_ref: str, db: Session = Depends(get_db)) -> AdminShiprocketDocOut:
    order = _order_for_docs(db, order_ref)
    oid = (order.shiprocket_order_id or "").strip()
    if not oid:
        raise HTTPException(status_code=400, detail="No Shiprocket order id on this order")
    try:
        res = print_invoice([oid])
    except ShiprocketError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    url = res.get("invoice_url") or ""
    return AdminShiprocketDocOut(
        kind="invoice",
        url=url,
        message="OK" if url else "Invoice requested — URL missing in Shiprocket response",
    )
