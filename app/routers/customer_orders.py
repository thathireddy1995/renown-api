"""Customer orders — /customer/orders (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

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
    track_by_awb,
)
from app.dto.order_dto import (
    OrderCreateRequest,
    OrderItemOut,
    OrderListResponse,
    OrderOut,
    OrderTrackingOut,
    PickupStoreOut,
    TrackingActivityOut,
)
from app.schemas import Customer, Order, OrderItem, Product, ProductVariant, Store, StoreOrder
from app.routers.customer_addresses import _out as _address_out

router = APIRouter(prefix="/customer/orders", tags=["customer-orders"])

STATUS_LABEL = {
    "placed": "Order Placed",
    "verified": "Prescription Verified",
    "packed": "Packed",
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
        date=order.created_at.strftime("%Y-%m-%d") if order.created_at else "",
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
        items=items,
    )


@router.get("/", response_model=OrderListResponse)
def list_orders(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
    page: tuple[int, int] = Depends(pagination),
) -> OrderListResponse:
    limit, offset = page
    total = (
        db.scalar(
            select(func.count())
            .select_from(Order)
            .where(Order.customer_id == customer.id)
        )
        or 0
    )
    rows = db.scalars(
        select(Order)
        .where(Order.customer_id == customer.id)
        .options(*_order_items_eager())
        .order_by(Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return OrderListResponse(
        items=[_order_out(r, db) for r in rows],
        total=total,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return _order_out(order, db)


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

    base = OrderTrackingOut(
        order_id=order.order_number,
        status=_status_label(order.status),
        awb_code=order.awb_code,
        courier_name=order.courier_name,
        tracking_url=order.tracking_url,
        shiprocket=False,
    )

    if not order.awb_code:
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

    # Keep Renown order status in sync with courier when it advances.
    mapped = info.get("mapped_status") or ""
    if mapped and mapped != (order.status or "").lower():
        order.status = mapped
        if info.get("courier") and not order.courier_name:
            order.courier_name = info["courier"][:120]
        if info.get("track_url"):
            order.tracking_url = info["track_url"]
        db.commit()

    return OrderTrackingOut(
        order_id=order.order_number,
        status=_status_label(order.status),
        awb_code=order.awb_code or info.get("awb") or None,
        courier_name=order.courier_name or info.get("courier") or None,
        tracking_url=order.tracking_url or info.get("track_url") or None,
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
    return _order_out(order, db)
