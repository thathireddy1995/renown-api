"""Customer orders — /customer/orders (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from datetime import datetime, timedelta, timezone

from app.core.ist import as_ist, format_ist_datetime, now as ist_now
from app.core.customer_prescription import upsert_from_cart_lines, upsert_from_lens_fit
from app.core.order_service import (
    create_order_record,
    load_cart_lines,
    resolve_shipping_address,
)
from app.core.product_resolve import public_product_id
from app.database import get_db
from app.deps import get_current_customer, pagination
from app.core.shiprocket import (
    ShiprocketError,
    configured as shiprocket_configured,
    normalize_tracking,
    should_advance_status,
    track_by_awb,
)
from app.core.order_lens_fit import (
    clean_eye,
    clean_patient,
    own_prescription_file,
    store_item_fits,
    store_order_notes,
)
from app.core.store_order_customer import (
    customer_store_orders_filter,
    load_customer_store_order,
    store_order_eager,
    store_order_out,
)
from app.core.shiprocket_fulfill import assign_awb_if_missing, attach_shiprocket_shipment
from app.dto.order_dto import (
    OrderCreateRequest,
    OrderItemLensFitIn,
    OrderItemOut,
    OrderListResponse,
    OrderOut,
    OrderTrackingOut,
    PickupStoreOut,
    TrackingActivityOut,
)
from app.schemas import Customer, Order, OrderItem, Product, ProductVariant, Store, StoreOrder
from app.routers.customer_addresses import _out as _address_out
from app.core.whatsapp_orders import notify_order_status, send_order_placed
from app.routers.telegram_notify import notify_order_placed

router = APIRouter(prefix="/customer/orders", tags=["customer-orders"])

STATUS_LABEL = {
    "placed": "Order Placed",
    "verified": "Prescription Verified",
    "packed": "Packed",
    "partner_assigned": "Delivery Partner Assigned",
    "shipped": "Shipped",
    "out": "Out for Delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}

def _status_label(raw: str) -> str:
    return STATUS_LABEL.get((raw or "").lower(), raw or "Order Placed")


def _clean_label(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() in ("__deleted__", "deleted"):
        return None
    return text


def _live_variants(variants: list[ProductVariant] | None) -> list[ProductVariant]:
    return [
        v
        for v in (variants or [])
        if (v.color or "") != "__deleted__" and (v.size or "") != "__deleted__"
    ]


def _order_items_eager():
    return (
        selectinload(Order.address),
        selectinload(Order.pickup_store),
        selectinload(Order.items)
        .selectinload(OrderItem.product)
        .selectinload(Product.brand),
        selectinload(Order.items)
        .selectinload(OrderItem.product)
        .selectinload(Product.category),
        selectinload(Order.items)
        .selectinload(OrderItem.product)
        .selectinload(Product.images),
        selectinload(Order.items)
        .selectinload(OrderItem.product)
        .selectinload(Product.variants)
        .selectinload(ProductVariant.color_ref),
        selectinload(Order.items)
        .selectinload(OrderItem.product)
        .selectinload(Product.variants)
        .selectinload(ProductVariant.size_ref),
        selectinload(Order.items)
        .selectinload(OrderItem.variant)
        .selectinload(ProductVariant.color_ref),
        selectinload(Order.items)
        .selectinload(OrderItem.variant)
        .selectinload(ProductVariant.size_ref),
    )


def _resolve_variant(item: OrderItem) -> ProductVariant | None:
    if item.variant is not None and (item.variant.color or "") != "__deleted__":
        return item.variant
    product = item.product
    if product:
        live = _live_variants(product.variants)
        if live:
            return live[0]
        if product.variants:
            return product.variants[0]
    return item.variant


def _order_item_out(item: OrderItem) -> OrderItemOut:
    product = item.product
    variant = _resolve_variant(item)
    color = None
    color_hex = None
    size = None
    variant_sku = None
    if variant is not None:
        color = _clean_label(
            (variant.color_ref.name if variant.color_ref else None) or variant.color
        )
        color_hex = (
            (variant.color_ref.hex if variant.color_ref else None) or variant.color_hex
        )
        size = _clean_label(
            (variant.size_ref.name if variant.size_ref else None) or variant.size
        )
        variant_sku = variant.sku
    image = None
    if product and product.images:
        image = product.images[0].url
    compare = float(product.compare_at_price) if product and product.compare_at_price is not None else None
    return OrderItemOut(
        itemId=item.id,
        productId=public_product_id(product) if product else str(item.product_id),
        name=item.name_snapshot or (product.name if product else ""),
        qty=item.qty,
        price=float(item.price_snapshot or 0),
        compare_at=compare,
        brand=product.brand.name if product and product.brand else None,
        category=product.category.name if product and product.category else None,
        sku=product.sku if product else None,
        variant_sku=variant_sku,
        color=color,
        color_hex=color_hex,
        size=size,
        frame_type=product.rim_type if product else None,
        shape=product.shape if product else None,
        material=product.material if product else None,
        gender=product.gender if product else None,
        warranty=product.warranty if product else None,
        description=product.description if product else None,
        image=image,
        lensFit=item.lens_fit,
    )


def _pickup_out(order: Order, db: Session | None = None) -> PickupStoreOut | None:
    store = order.pickup_store
    if store is None and db is not None:
        store_id = getattr(order, "pickup_store_id", None)
        if store_id:
            store = db.get(Store, store_id)
        if store is None:
            so = db.scalar(
                select(StoreOrder)
                .where(StoreOrder.order_number == order.order_number)
                .options(selectinload(StoreOrder.store))
            )
            if so and so.store:
                store = so.store
            elif so:
                store = db.get(Store, so.store_id)
    if store is None:
        return None
    return PickupStoreOut(
        id=store.id,
        name=store.name,
        city=store.city or "",
        address=store.address or "",
        phone=store.phone or "",
    )


def _order_out(order: Order, db: Session | None = None) -> OrderOut:
    items = [_order_item_out(i) for i in (order.items or [])]
    delivery = (getattr(order, "delivery", None) or "ship").lower()
    pickup = _pickup_out(order, db)
    if pickup and delivery != "pickup":
        delivery = "pickup"
    address = _address_out(order.address) if order.address else None
    return OrderOut(
        id=order.order_number,
        date=format_ist_datetime(order.created_at),
        status=_status_label(order.status),
        total=float(order.total or 0),
        subtotal=float(order.subtotal or 0),
        discount=float(order.discount or 0),
        shipping=float(order.shipping_fee or 0),
        tax=float(order.tax or 0),
        coupon_code=order.coupon_code,
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        delivery=delivery,
        address=address,
        pickup_store=pickup,
        awb_code=order.awb_code,
        courier_name=order.courier_name,
        tracking_url=order.tracking_url,
        shiprocket_order_id=order.shiprocket_order_id,
        shiprocket_shipment_id=order.shiprocket_shipment_id,
        verify_token=order.verify_token,
        items=items,
    )


@router.get("/", response_model=OrderListResponse)
def list_orders(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
    page: tuple[int, int] = Depends(pagination),
) -> OrderListResponse:
    limit, offset = page
    web_total = (
        db.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.customer_id == customer.id)
        )
        or 0
    )
    store_filter = customer_store_orders_filter(customer.id)
    store_total = db.scalar(select(func.count()).select_from(StoreOrder).where(*store_filter)) or 0
    # Merge both sources newest-first; each side needs at most offset+limit rows.
    window = offset + limit
    web_rows = db.scalars(
        select(Order)
        .where(Order.customer_id == customer.id)
        .options(*_order_items_eager())
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(window)
    ).all()
    store_rows = (
        db.scalars(
            select(StoreOrder)
            .where(*store_filter)
            .options(*store_order_eager())
            .order_by(StoreOrder.created_at.desc(), StoreOrder.id.desc())
            .limit(window)
        ).all()
        if store_total
        else []
    )
    merged = sorted(
        [(r.created_at, _order_out(r, db)) for r in web_rows]
        + [(r.created_at, store_order_out(r)) for r in store_rows],
        key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return OrderListResponse(
        items=[out for _, out in merged[offset:window]],
        total=web_total + store_total,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_number}", response_model=OrderOut)
def get_order(
    order_number: str,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderOut:
    order = db.scalar(
        select(Order)
        .where(
            Order.order_number == order_number,
            Order.customer_id == customer.id,
        )
        .options(*_order_items_eager())
    )
    if not order:
        store_order = load_customer_store_order(db, customer.id, order_number)
        if store_order:
            return store_order_out(store_order)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return _order_out(order, db)


POWER_LATER_DAYS = 15
POWER_LATER_STATUSES = ("placed", "verified")


@router.patch("/{order_number}/items/{item_id}/lens-fit", response_model=OrderOut)
def submit_item_power(
    order_number: str,
    item_id: int,
    payload: OrderItemLensFitIn,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderOut:
    """Attach power to a line ordered with "send power later"."""
    order = db.scalar(
        select(Order)
        .where(Order.order_number == order_number, Order.customer_id == customer.id)
        .options(*_order_items_eager())
        .with_for_update(of=Order)
    )
    if not order:
        store_order = load_customer_store_order(db, customer.id, order_number, for_update=True)
        if not store_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
        _check_power_window(store_order.created_at, (store_order.status or "").lower() == "pending")
        fits = store_item_fits(store_order)
        line, current = next(((i, f) for i, f in fits if i.id == item_id), (None, None))
        if line is None or current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
        updated = _merged_power(current, payload, customer.id)
        line.lens_fit = updated
        if store_order.lens_fit and fits[0][0].id == line.id:
            store_order.lens_fit = updated
        store_order.notes = store_order_notes([updated if i.id == line.id else f for i, f in fits])
        upsert_from_lens_fit(db, customer.id, updated)
        db.commit()
        return store_order_out(load_customer_store_order(db, customer.id, order_number))

    _check_power_window(order.created_at, (order.status or "").lower() in POWER_LATER_STATUSES)
    item = next((i for i in order.items or [] if i.id == item_id), None)
    current = item.lens_fit if item is not None and isinstance(item.lens_fit, dict) else None
    if item is None or current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found.")
    updated = _merged_power(current, payload, customer.id)
    item.lens_fit = updated
    upsert_from_lens_fit(db, customer.id, updated)
    db.commit()
    db.refresh(order)
    return _order_out(order, db)


def _check_power_window(created_at, status_ok: bool) -> None:
    if not status_ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This order is already being processed. Please call support to update power.",
        )
    if created_at and ist_now() - as_ist(created_at) > timedelta(days=POWER_LATER_DAYS):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Power can only be added within {POWER_LATER_DAYS} days of ordering.",
        )


def _merged_power(current: dict, payload: OrderItemLensFitIn, customer_id: int) -> dict:
    if str(current.get("source") or "").lower() != "later":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Power is already on file for this item."
        )

    incoming = payload.lensFit
    rx = incoming.get("prescription") if isinstance(incoming.get("prescription"), dict) else {}
    right = clean_eye(rx.get("right"))
    left = clean_eye(rx.get("left"))
    file = own_prescription_file(incoming.get("prescriptionFile"), customer_id)
    has_file = file is not None
    has_rx = bool(right["sph"] and left["sph"])
    if not has_file and not has_rx:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add SPH for both eyes or upload your prescription.",
        )

    source = str(incoming.get("source") or "").lower()
    updated: dict = {
        "powerMode": current.get("powerMode") or "powered",
        "lensType": current.get("lensType") or "",
        "source": source if source in ("manual", "saved", "upload") else ("upload" if has_file else "manual"),
    }
    patient = clean_patient(incoming.get("patient") or current.get("patient"))
    if patient:
        updated["patient"] = patient
    if has_rx:
        updated["prescription"] = {"right": right, "left": left}
    if has_file:
        updated["prescriptionFile"] = file
    return updated


@router.get("/{order_number}/tracking", response_model=OrderTrackingOut)
def track_order(
    order_number: str,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderTrackingOut:
    """Order timeline + live Shiprocket events when an AWB is attached."""
    order = db.scalar(
        select(Order).where(
            Order.order_number == order_number,
            Order.customer_id == customer.id,
        )
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")

    if not order.awb_code and order.shiprocket_shipment_id:
        assign_awb_if_missing(db, order)
        db.refresh(order)

    base = OrderTrackingOut(
        order_id=order.order_number,
        status=_status_label(order.status),
        awb_code=order.awb_code,
        courier_name=order.courier_name,
        tracking_url=order.tracking_url,
        shiprocket_order_id=order.shiprocket_order_id,
        shiprocket_shipment_id=order.shiprocket_shipment_id,
        shiprocket=False,
    )

    if not order.awb_code:
        if order.shiprocket_shipment_id:
            base.message = "Shipment booked. Courier AWB will appear once assigned."
        else:
            base.message = "Shipment not handed to courier yet."
        return base

    if not shiprocket_configured():
        base.message = "Tracking service is not configured."
        return base

    try:
        raw = track_by_awb(order.awb_code)
        info = normalize_tracking(raw)
    except ShiprocketError as err:
        base.message = str(err)
        return base

    if info.get("error"):
        base.message = str(info["error"])
        return base

    dirty = False
    previous_status = order.status
    mapped = info.get("mapped_status") or ""
    if should_advance_status(order.status, mapped):
        order.status = mapped
        dirty = True
    if info.get("courier") and not order.courier_name:
        order.courier_name = str(info["courier"])[:120]
        dirty = True
    if info.get("track_url") and not order.tracking_url:
        order.tracking_url = str(info["track_url"])
        dirty = True
    if dirty:
        db.commit()
        notify_order_status(order, previous_status)

    return OrderTrackingOut(
        order_id=order.order_number,
        status=_status_label(order.status),
        awb_code=order.awb_code or info.get("awb") or None,
        courier_name=order.courier_name or info.get("courier") or None,
        tracking_url=order.tracking_url or info.get("track_url") or None,
        shiprocket_order_id=order.shiprocket_order_id,
        shiprocket_shipment_id=order.shiprocket_shipment_id,
        current_status=info.get("current_status") or None,
        edd=info.get("edd") or None,
        origin=info.get("origin") or None,
        destination=info.get("destination") or None,
        activities=[TrackingActivityOut(**a) for a in info.get("activities") or []],
        shiprocket=True,
        message=None,
    )


@router.post("/", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreateRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> OrderOut:
    """Cash-on-delivery / no-gateway checkout. Online payments go through
    /customer/payments (see customer_payments.py) — an Order row there is
    only written *after* Razorpay confirms the payment."""
    line_rows, subtotal = load_cart_lines(db, customer)
    delivery = payload.delivery or "ship"
    address_id = resolve_shipping_address(db, customer, payload.address_id, delivery)

    # Snapshot Rx onto the customer profile before create_order_record commits
    # and deletes cart rows (expired CartItem.lens_fit would fail after that).
    upsert_from_cart_lines(db, customer.id, line_rows)
    order = create_order_record(
        db,
        customer,
        address_id=address_id,
        delivery=delivery,
        pickup_store_id=payload.pickup_store_id,
        coupon_code=payload.coupon_code,
        line_rows=line_rows,
        subtotal=subtotal,
        payment_method="cod",
        payment_status="pending",
    )
    attach_shiprocket_shipment(db, order, customer)
    db.refresh(order)
    notify_order_placed(order, customer)
    send_order_placed(order, customer)
    return _order_out(order, db)
