"""Counter (store app) orders as the customer sees them on the website / app.

A store manager places the order on the customer's behalf after OTP, so it is
linked by customer_id and shows up in /customer/orders next to web orders.
Web click & collect orders also create a StoreOrder with the same order_number;
those are skipped here because the web Order is the customer's copy.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import JWT_SECRET
from app.core.ist import format_ist_datetime
from app.core.order_lens_fit import store_item_fits
from app.core.product_resolve import public_product_id
from app.dto.order_dto import AddressOut, OrderItemOut, OrderOut, PickupStoreOut
from app.schemas import Order, Product, ProductVariant, StoreOrder, StoreOrderItem

STORE_STATUS_LABEL = {
    "pending": "Order Placed",
    "ordered": "Order Placed",
    "preparing": "At Lab",
    "processing": "At Lab",
    "collected": "Collected",
    "completed": "Collected",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
    "missed": "Cancelled",
    "void": "Cancelled",
}

PAYMENT_LABEL = {"cash": "Cash", "card": "Card", "upi": "UPI", "online": "Online"}

_TOKEN_RE = re.compile(r"^S(\d{1,12})-([0-9a-f]{24})$")


def _sign(order_id: int) -> str:
    key = (JWT_SECRET or "renown-store-invoice").encode()
    return hmac.new(key, f"store-invoice:{order_id}".encode(), hashlib.sha256).hexdigest()[:24]


def store_invoice_token(order: StoreOrder) -> str:
    """Unguessable invoice link token — no DB column needed."""
    return f"S{order.id}-{_sign(order.id)}"


def store_order_id_from_token(token: str) -> int | None:
    match = _TOKEN_RE.match(token or "")
    if not match:
        return None
    order_id = int(match.group(1))
    return order_id if hmac.compare_digest(match.group(2), _sign(order_id)) else None


def invoice_token_for(db: Session, order: StoreOrder) -> str:
    """Invoice token for WhatsApp links: the web twin's token when it exists."""
    web_token = db.scalar(select(Order.verify_token).where(Order.order_number == order.order_number))
    return web_token or store_invoice_token(order)


def store_order_eager():
    variant = selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant)
    return (
        selectinload(StoreOrder.store),
        variant.selectinload(ProductVariant.color_ref),
        variant.selectinload(ProductVariant.size_ref),
        variant.selectinload(ProductVariant.product).selectinload(Product.brand),
        variant.selectinload(ProductVariant.product).selectinload(Product.category),
        variant.selectinload(ProductVariant.product).selectinload(Product.images),
    )


def customer_store_orders_filter(customer_id: int):
    """Counter orders for this customer that have no web Order twin."""
    return (
        StoreOrder.customer_id == customer_id,
        ~exists().where(Order.order_number == StoreOrder.order_number),
    )


def load_customer_store_order(
    db: Session, customer_id: int, order_number: str, *, for_update: bool = False
) -> StoreOrder | None:
    stmt = (
        select(StoreOrder)
        .where(StoreOrder.order_number == order_number, *customer_store_orders_filter(customer_id))
        .options(*store_order_eager())
    )
    if for_update:
        stmt = stmt.with_for_update(of=StoreOrder)
    return db.scalar(stmt)


def store_status_label(order: StoreOrder) -> str:
    key = (order.status or "").lower()
    if key == "ready":
        return "Ready for Pickup" if order.channel == "click_collect" else "Ready for Dispatch"
    return STORE_STATUS_LABEL.get(key, order.status or "Order Placed")


def store_payment_label(order: StoreOrder) -> str:
    method = PAYMENT_LABEL.get((order.payment_method or "").lower(), (order.payment_method or "").title())
    store = order.store.name if order.store else "store"
    return f"Paid at {store} ({method})" if method else f"Paid at {store}"


def _item_out(item: StoreOrderItem, lens_fit: dict | None) -> OrderItemOut:
    variant = item.variant
    product = variant.product if variant else None
    color = (variant.color_ref.name if variant and variant.color_ref else None) or (variant.color if variant else None)
    size = (variant.size_ref.name if variant and variant.size_ref else None) or (variant.size if variant else None)
    return OrderItemOut(
        itemId=item.id,
        productId=public_product_id(product) if product else "",
        name=(product.name if product else None) or (variant.sku if variant else "Item"),
        qty=int(item.qty or 1),
        price=float(item.price_snapshot or 0),
        brand=product.brand.name if product and product.brand else None,
        category=product.category.name if product and product.category else None,
        sku=product.sku if product else None,
        variant_sku=variant.sku if variant else None,
        color=None if color == "__deleted__" else color,
        color_hex=(variant.color_ref.hex if variant and variant.color_ref else None) or (variant.color_hex if variant else None),
        size=None if size == "__deleted__" else size,
        frame_type=product.rim_type if product else None,
        shape=product.shape if product else None,
        material=product.material if product else None,
        image=product.images[0].url if product and product.images else None,
        lensFit=lens_fit,
    )


def store_order_out(order: StoreOrder, *, include_phone: bool = True) -> OrderOut:
    items = [_item_out(item, fit) for item, fit in store_item_fits(order)]
    store = order.store
    pickup = (
        PickupStoreOut(
            id=store.id,
            name=store.name,
            city=store.city or "",
            address=store.address or "",
            phone=store.phone or "",
        )
        if store
        else None
    )
    buyer = AddressOut(
        id=f"store-{order.id}",
        name=order.customer_name or "Customer",
        line1=f"Purchased at {store.name}" if store else "Purchased in store",
        line2=(store.address or None) if store else None,
        city=(store.city or "") if store else "",
        phone=(order.customer_phone or "") if include_phone else "",
        country=(store.country or "India") if store else "India",
    )
    total = float(order.total or 0)
    return OrderOut(
        id=order.order_number,
        date=format_ist_datetime(order.created_at),
        status=store_status_label(order),
        total=total,
        subtotal=float(order.subtotal or total),
        tax=0,
        payment_method=store_payment_label(order),
        payment_status="paid",
        delivery="pickup" if order.channel == "click_collect" else "ship",
        address=buyer,
        pickup_store=pickup if order.channel == "click_collect" else None,
        verify_token=store_invoice_token(order),
        channel="store",
        fulfillment="store_pickup" if order.channel == "click_collect" else "home_delivery",
        store_name=store.name if store else None,
        items=items,
    )
