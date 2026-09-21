"""Create a Shiprocket shipment after a Renown home-delivery order is saved."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.company_settings import _FALLBACK, company_details
from app.core.ist import format_ist_datetime, naive_now, now
from app.core.config import (
    SHIPROCKET_DEFAULT_BREADTH_CM,
    SHIPROCKET_DEFAULT_HEIGHT_CM,
    SHIPROCKET_DEFAULT_LENGTH_CM,
    SHIPROCKET_DEFAULT_WEIGHT_KG,
    SHIPROCKET_PICKUP_LOCATION,
)
from app.core.shiprocket import (
    ShiprocketError,
    add_pickup_location,
    assign_awb,
    check_serviceability,
    configured,
    create_adhoc_order,
    get_order,
    get_shipment,
    list_pickup_locations,
    request_pickup,
)
from app.schemas import Customer, Order, OrderItem

logger = logging.getLogger(__name__)


def _digits_phone(raw: str | None) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[-10:]
    return digits


def _pincode(raw: str | None) -> str:
    digits = re.sub(r"\D", "", raw or "")
    return digits[:6]


def _split_name(raw: str | None) -> tuple[str, str]:
    parts = [p for p in (raw or "").strip().split() if p]
    if not parts:
        return "Customer", "."
    first = parts[0][:50]
    last = " ".join(parts[1:])[:50] if len(parts) > 1 else "."
    return first, last


def _pickup_nickname(row: dict[str, Any]) -> str:
    return str(
        row.get("pickup_location")
        or row.get("pickup_location_name")
        or row.get("name")
        or ""
    ).strip()


def _ensure_pickup_location(db: Session) -> str:
    wanted = SHIPROCKET_PICKUP_LOCATION
    existing = list_pickup_locations()
    names = {_pickup_nickname(row) for row in existing if _pickup_nickname(row)}
    if wanted in names:
        return wanted
    if names:
        return next(iter(names))

    try:
        company = company_details(db)
    except Exception:
        company = _FALLBACK
    phone = _digits_phone(company.phone)
    add_pickup_location(
        {
            "pickup_location": wanted,
            "name": (company.legal_name or company.brand_name or "Renown")[:50],
            "email": company.email or "support@renowneyewear.com",
            "phone": phone or "9642512952",
            "address": (company.address_line1 or "Warehouse")[:80],
            "address_2": (company.address_line2 or "")[:80],
            "city": company.city or "Tirupati",
            "state": company.state or "Andhra Pradesh",
            "country": company.country or "India",
            "pin_code": _pincode(company.postal_code) or "517508",
        }
    )
    return wanted


def _order_items_payload(order: Order) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in order.items or []:
        qty = int(item.qty or 0)
        if qty <= 0:
            continue
        product = item.product
        variant = item.variant
        sku = (
            (variant.sku if variant and variant.sku else None)
            or (product.sku if product and product.sku else None)
            or f"ITEM-{item.id}"
        )
        name = (item.name_snapshot or (product.name if product else None) or sku)[:200]
        price = float(item.price_snapshot or 0)
        rows.append(
            {
                "name": name,
                "sku": str(sku)[:50],
                "units": qty,
                "selling_price": max(price, 1),
            }
        )
    return rows


def _build_adhoc_payload(db: Session, order: Order, customer: Customer) -> dict[str, Any]:
    address = order.address
    if address is None:
        raise ShiprocketError("Home-delivery order has no shipping address")

    first, last = _split_name(customer.name or address.label or "Customer")
    phone = _digits_phone(address.phone or customer.phone)
    if len(phone) != 10:
        raise ShiprocketError("A 10-digit mobile number is required to book Shiprocket")
    pin = _pincode(address.postal_code)
    if len(pin) != 6:
        raise ShiprocketError("A 6-digit pincode is required to book Shiprocket")

    items = _order_items_payload(order)
    if not items:
        raise ShiprocketError("Order has no items to ship")

    email = (customer.email or "").strip() or f"order-{order.order_number.lower()}@renowneyewear.com"
    prepaid = (order.payment_method or "").lower() == "razorpay" and (
        order.payment_status or ""
    ).lower() == "paid"
    line2 = (address.line2 or "").strip()
    city = (address.city or "").strip() or "City"
    state = (address.state or "").strip() or "Andhra Pradesh"

    return {
        "order_id": order.order_number,
        "order_date": format_ist_datetime(order.created_at) or now().strftime("%Y-%m-%d %H:%M"),
        "pickup_location": _ensure_pickup_location(db),
        "billing_customer_name": first,
        "billing_last_name": last,
        "billing_address": (address.line1 or "")[:80],
        "billing_address_2": line2[:80],
        "billing_city": city[:50],
        "billing_pincode": pin,
        "billing_state": state[:50],
        "billing_country": (address.country or "India")[:50],
        "billing_email": email[:80],
        "billing_phone": phone,
        "shipping_is_billing": True,
        "order_items": items,
        "payment_method": "Prepaid" if prepaid else "COD",
        "sub_total": float(order.subtotal or order.total or 0) or 1,
        "length": SHIPROCKET_DEFAULT_LENGTH_CM,
        "breadth": SHIPROCKET_DEFAULT_BREADTH_CM,
        "height": SHIPROCKET_DEFAULT_HEIGHT_CM,
        "weight": SHIPROCKET_DEFAULT_WEIGHT_KG,
    }


def attach_shiprocket_shipment(
    db: Session, order: Order, customer: Customer | None = None
) -> None:
    """Best-effort: create Shiprocket order + AWB. Never fails the customer checkout."""
    if not configured():
        return
    if (order.delivery or "ship").lower() == "pickup":
        return
    if order.shiprocket_shipment_id:
        return

    cust = customer or order.customer
    if cust is None:
        logger.warning("Shiprocket skip %s: no customer", order.order_number)
        return

    try:
        loaded = db.scalar(_order_query(order.id))
        if loaded:
            order = loaded
        payload = _build_adhoc_payload(db, order, cust)
        created = create_adhoc_order(payload)
    except ShiprocketError as err:
        logger.warning("Shiprocket create failed for %s: %s", order.order_number, err)
        return
    except Exception:
        logger.exception("Shiprocket create failed for %s", order.order_number)
        return

    order.shiprocket_order_id = created["order_id"] or None
    order.shiprocket_shipment_id = created["shipment_id"]
    # AWB / courier are chosen later by warehouse (admin partner assign).
    # Stash any courier Shiprocket may have echoed, but do not auto-assign here.
    if created.get("awb_code"):
        order.awb_code = created["awb_code"][:80]
    if created.get("courier_name") and not order.courier_name:
        order.courier_name = created["courier_name"][:120]

    if order.awb_code and not order.tracking_url:
        order.tracking_url = f"https://shiprocket.co/tracking/{order.awb_code}"

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Shiprocket ids could not be saved for %s", order.order_number)
        return


def _order_query(order_id: int):
    return (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.items).selectinload(OrderItem.variant),
            selectinload(Order.address),
            selectinload(Order.customer),
        )
    )


def pickup_postcode(db: Session) -> str:
    """Pin for the configured Shiprocket pickup nickname (Store / Primary)."""
    wanted = SHIPROCKET_PICKUP_LOCATION
    try:
        for row in list_pickup_locations():
            if _pickup_nickname(row) == wanted:
                pin = _pincode(str(row.get("pin_code") or row.get("pickup_code") or ""))
                if len(pin) == 6:
                    return pin
    except ShiprocketError:
        pass
    try:
        company = company_details(db)
        pin = _pincode(company.postal_code)
        if len(pin) == 6:
            return pin
    except Exception:
        pass
    return "517501" if wanted == "Store" else "517508"


def list_couriers_for_order(db: Session, order: Order) -> list[dict[str, Any]]:
    """Serviceable couriers for an order's ship-to pin (COD-aware)."""
    if not configured():
        raise ShiprocketError("Shiprocket credentials are not configured")
    address = order.address
    if address is None:
        raise ShiprocketError("Order has no shipping address")
    delivery = _pincode(address.postal_code)
    if len(delivery) != 6:
        raise ShiprocketError("A 6-digit delivery pincode is required")
    prepaid = (order.payment_method or "").lower() == "razorpay" and (
        order.payment_status or ""
    ).lower() == "paid"
    return check_serviceability(
        pickup_postcode=pickup_postcode(db),
        delivery_postcode=delivery,
        weight_kg=SHIPROCKET_DEFAULT_WEIGHT_KG,
        cod=not prepaid,
        length_cm=SHIPROCKET_DEFAULT_LENGTH_CM,
        breadth_cm=SHIPROCKET_DEFAULT_BREADTH_CM,
        height_cm=SHIPROCKET_DEFAULT_HEIGHT_CM,
    )


def _parse_shiprocket_dt(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw or raw.upper() in ("NA", "N/A", "-"):
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%d-%b-%Y %H:%M",
        "%d %b %Y %I:%M %p",
        "%d %b %Y",
        "%d-%b-%Y",
    ):
        try:
            return datetime.strptime(raw.replace("st ", " ").replace("nd ", " ").replace("rd ", " ").replace("th ", " "), fmt)
        except ValueError:
            continue
    # Fall back: date-only like "22-Sep-2026"
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def sync_pickup_meta_for_order(db: Session, order: Order) -> None:
    """Pull pickup scheduled / generated timestamps from Shiprocket onto the order."""
    if not configured():
        return
    scheduled = None
    generated = None
    try:
        if order.shiprocket_order_id:
            data = get_order(order.shiprocket_order_id)
            ship = data.get("shipments") if isinstance(data, dict) else None
            if isinstance(ship, dict):
                scheduled = (
                    str(ship.get("pickup_scheduled_date") or "").strip() or None
                )
            if isinstance(data, dict) and not scheduled:
                scheduled = (
                    str(data.get("pickup_scheduled_date") or "").strip() or None
                )
        if order.shiprocket_shipment_id:
            ship = get_shipment(order.shiprocket_shipment_id)
            if isinstance(ship, dict):
                generated = _parse_shiprocket_dt(ship.get("pickup_generated_date"))
                if not scheduled:
                    scheduled = (
                        str(ship.get("pickup_scheduled_date") or "").strip() or None
                    )
    except ShiprocketError as err:
        logger.warning("Shiprocket pickup meta failed for %s: %s", order.order_number, err)
        return
    except Exception:
        logger.exception("Shiprocket pickup meta failed for %s", order.order_number)
        return

    dirty = False
    if scheduled and scheduled != (order.pickup_scheduled_date or ""):
        order.pickup_scheduled_date = scheduled[:40]
        dirty = True
    if generated and order.pickup_generated_at != generated:
        order.pickup_generated_at = generated
        dirty = True
    if dirty:
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not save pickup meta for %s", order.order_number)


def request_pickup_for_order(db: Session, order: Order) -> None:
    if not configured() or not order.shiprocket_shipment_id:
        return
    try:
        request_pickup(order.shiprocket_shipment_id)
    except ShiprocketError as err:
        logger.warning("Shiprocket pickup failed for %s: %s", order.order_number, err)
    except Exception:
        logger.exception("Shiprocket pickup failed for %s", order.order_number)
        return
    # Persist schedule so Online deliveries can show it without live SR calls.
    if not order.pickup_generated_at:
        order.pickup_generated_at = naive_now()
        try:
            db.commit()
        except Exception:
            db.rollback()
    sync_pickup_meta_for_order(db, order)


def assign_awb_if_missing(
    db: Session,
    order: Order,
    *,
    courier_id: int | str | None = None,
) -> None:
    if not configured() or order.awb_code or not order.shiprocket_shipment_id:
        return
    try:
        assigned = assign_awb(order.shiprocket_shipment_id, courier_id=courier_id)
    except ShiprocketError as err:
        logger.warning("Shiprocket AWB retry failed for %s: %s", order.order_number, err)
        return
    except Exception:
        logger.exception("Shiprocket AWB retry failed for %s", order.order_number)
        return
    order.awb_code = assigned["awb_code"][:80]
    if assigned.get("courier_name"):
        order.courier_name = assigned["courier_name"][:120]
    if not order.tracking_url:
        order.tracking_url = f"https://shiprocket.co/tracking/{order.awb_code}"
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Shiprocket AWB retry could not be saved for %s", order.order_number)
