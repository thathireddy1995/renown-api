"""Store manager tablet APIs — /store/app.

Lambda-friendly: batched joins, no per-row queries. Auth is the existing
store_manager JWT from POST /staff/auth/login.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import IS_PRODUCTION, OTP_EXPIRY_MINUTES, S3_PUBLIC_BUCKET
from app.core.customer_prescription import (
    get_for_customer,
    summary_for,
    to_out,
    upsert_for_customer,
    upsert_from_lens_fit,
)
from app.core.ist import now as ist_now
from app.core.order_lens_fit import (
    is_power_later,
    labels_from_lens_fit,
    lens_fits_by_order_numbers,
    recent_lens_fits,
    sanitize_lens_fit,
    store_item_fits,
    store_order_notes,
)
from app.core.pickup_otp import consume_pickup_otp, send_pickup_otp
from app.core.s3_images import presign_prescription_puts
from app.core.customer_name import has_real_name, placeholder_name
from app.core.store_order_customer import invoice_token_for, store_invoice_token
from app.core.whatsapp_orders import notify_store_order_status, send_store_order_placed
from app.core.staff_users import digits_phone
from app.core.whatsapp_otp import WhatsAppOtpError, send_whatsapp_otp
from app.database import get_db
from app.deps import pagination, require_role, TokenPrincipal
from app.dto.catalog_dto import ImagePresignItem, ImagePresignRequest, ImagePresignResponse
from app.dto.prescription_dto import CustomerPrescriptionUpsert, EyeRxIn
from app.dto.store_app_dto import (
    StoreAppCustomerOut,
    StoreAppHomeOut,
    StoreAppLensFitPatch,
    StoreAppLensTypeOut,
    StoreAppLocationOut,
    StoreAppMeOut,
    StoreAppOrderLineIn,
    StoreAppOrderLineOut,
    StoreAppOrderListOut,
    StoreAppOrderOut,
    StoreAppOtpRequest,
    StoreAppOtpResponse,
    StoreAppOtpVerify,
    StoreAppPlaceOrderRequest,
    StoreAppStatusPatch,
    StoreAppStockListOut,
    StoreAppStockOut,
)
from app.schemas import (
    Category,
    Customer,
    LensType,
    OtpCode,
    Product,
    ProductVariant,
    Store,
    StoreInventory,
    StoreOrder,
    StoreOrderItem,
    User,
)

router = APIRouter(
    prefix="/store/app",
    tags=["store-app"],
    dependencies=[Depends(require_role("store_manager"))],
)

OTP_PURPOSE = "store_verify"
ORDER_OTP_WINDOW = timedelta(hours=12)

OPEN_STATUSES = ("Pending", "Preparing", "Ready", "Processing", "Ordered")
CLOSED_STATUSES = ("Collected", "Delivered", "Completed", "Cancelled", "Missed", "Void")

STATUS_TO_APP = {
    "pending": "ordered",
    "ordered": "ordered",
    "preparing": "atLab",
    "processing": "atLab",
    "ready": "readyForPickup",
    "collected": "handedOver",
    "completed": "handedOver",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "missed": "cancelled",
    "void": "cancelled",
}

APP_TO_STATUS = {
    "ordered": "Pending",
    "atLab": "Preparing",
    "readyForPickup": "Ready",
    "handedOver": "Collected",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def _require_store(db: Session, principal: TokenPrincipal) -> Store:
    if principal.store_id is None:
        raise HTTPException(status_code=403, detail="Store manager is not linked to a store")
    store = db.get(Store, principal.store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


def _load_store_order(db: Session, store_id: int, order_ref: str) -> StoreOrder:
    stmt = (
        select(StoreOrder)
        .options(
            selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant).selectinload(ProductVariant.product)
        )
        .where(StoreOrder.store_id == store_id)
    )
    order = db.scalar(stmt.where(StoreOrder.order_number == order_ref))
    if not order and order_ref.isdigit():
        order = db.scalar(stmt.where(StoreOrder.id == int(order_ref)))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def _location_out(store: Store) -> StoreAppLocationOut:
    return StoreAppLocationOut(
        kind="store",
        id=store.id,
        code=store.code,
        name=store.name,
        address=store.address or "",
        city=store.city or "",
        country=store.country or "",
        phone=store.phone or "",
    )


def _phone10(raw: str | None) -> str:
    phone = digits_phone(raw)
    if len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    if len(phone) != 10:
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit phone number")
    return phone


def _item_name(item: StoreOrderItem) -> str:
    variant = item.variant
    if variant is None:
        return "—"
    product = variant.product
    return product.name if product is not None else (variant.sku or "—")


def _frame_name(order: StoreOrder) -> str:
    names = [_item_name(i) for i in sorted(order.items or [], key=lambda i: i.id or 0)]
    return " + ".join(names) if names else "—"


def _line_outs(fits: list[tuple[StoreOrderItem, dict | None]]) -> list[StoreAppOrderLineOut]:
    out = []
    for item, fit in fits:
        lens, power = labels_from_lens_fit(fit)
        out.append(
            StoreAppOrderLineOut(
                item_id=item.id,
                name=_item_name(item),
                sku=item.variant.sku if item.variant else "",
                price=float(item.price_snapshot or 0),
                lens_type=lens,
                power=power,
                lens_fit=fit,
            )
        )
    return out


def _order_out(
    order: StoreOrder,
    lens_fit: dict | None = None,
    fits: list[tuple[StoreOrderItem, dict | None]] | None = None,
) -> StoreAppOrderOut:
    notes = (order.notes or "").strip()
    lens = ""
    power = ""
    if " · " in notes:
        lens, _, power = notes.partition(" · ")
    elif notes:
        lens = notes
    fit_lens, fit_power = labels_from_lens_fit(lens_fit)
    if fit_lens:
        lens = fit_lens
    if fit_power:
        power = fit_power
    pickup = None
    if order.pickup_at:
        pickup = order.pickup_at.isoformat()
    phone = digits_phone(order.customer_phone) or ""
    return StoreAppOrderOut(
        id=order.order_number,
        db_id=order.id,
        customer_name=order.customer_name or "Customer",
        customer_phone=phone,
        frame_name=_frame_name(order),
        lens_type=lens,
        power=power,
        status=STATUS_TO_APP.get((order.status or "").lower(), "ordered"),
        fulfillment="home_delivery" if order.channel == "home_delivery" else "store_pickup",
        payment=(order.payment_method or "cash").lower(),
        amount=float(order.total or 0),
        created_at=order.created_at.isoformat() if order.created_at else "",
        pickup_at=pickup,
        serial=None,
        lens_fit=lens_fit,
        items=_line_outs(fits or []),
    )


def _own_fits(order: StoreOrder) -> list[tuple[StoreOrderItem, dict | None]] | None:
    fits = store_item_fits(order)
    return fits if any(f for _, f in fits) else None


def _headline_fit(fits: list[tuple[StoreOrderItem, dict | None]]) -> dict | None:
    """Single fit for the order row: the line still waiting for power, else the first."""
    present = [f for _, f in fits if f]
    return next((f for f in present if is_power_later(f)), present[0] if present else None)


def _order_outs(db: Session, orders: list[StoreOrder | None]) -> list[StoreAppOrderOut]:
    rows = [o for o in orders if o is not None]
    web = lens_fits_by_order_numbers(db, [o.order_number for o in rows if _own_fits(o) is None])
    out = []
    for o in rows:
        fits = _own_fits(o)
        if fits is None:
            fits = store_item_fits(o)
            if fits and web.get(o.order_number):
                fits[0] = (fits[0][0], web[o.order_number])
        out.append(_order_out(o, _headline_fit(fits), fits))
    return out


def _get_or_create_customer(db: Session, phone: str) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer:
        if not customer.is_active:
            customer.is_active = True
        return customer
    customer = Customer(phone=phone, name=placeholder_name(phone), is_active=True)
    db.add(customer)
    db.flush()
    return customer


def _customer_out(db: Session, customer: Customer, phone: str) -> StoreAppCustomerOut:
    saved = get_for_customer(db, customer.id)
    summary = summary_for(saved)
    past = db.scalar(select(func.count()).select_from(StoreOrder).where(StoreOrder.customer_id == customer.id)) or 0
    return StoreAppCustomerOut(
        phone=phone,
        name=customer.name or f"Customer {phone[-4:]}",
        email=customer.email,
        power_summary=summary,
        saved_rx=summary or None,
        past_order_count=int(past),
        prescription=to_out(saved) if saved else None,
        recent_fits=recent_lens_fits(db, customer.id),
    )


@router.get("/me", response_model=StoreAppMeOut)
def me(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppMeOut:
    store = _require_store(db, principal)
    user = db.get(User, principal.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return StoreAppMeOut(
        id=user.id,
        name=user.name,
        phone=user.phone or "",
        email=user.email,
        role=user.role,
        location=_location_out(store),
    )


@router.get("/home", response_model=StoreAppHomeOut)
def home(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppHomeOut:
    store = _require_store(db, principal)

    qty = StoreInventory.on_floor + StoreInventory.backroom
    stats = db.execute(
        select(
            func.count().filter(StoreOrder.status.in_(OPEN_STATUSES)).label("open_orders"),
            func.count()
            .filter(
                StoreOrder.channel == "click_collect",
                StoreOrder.status.in_(("Ready", "Preparing", "Pending")),
            )
            .label("pickups_today"),
        )
        .select_from(StoreOrder)
        .where(StoreOrder.store_id == store.id)
    ).one()

    inv_stats = db.execute(
        select(
            func.count().label("sku_count"),
            func.count().filter(qty <= func.coalesce(StoreInventory.reorder_point, 3)).label("low_stock"),
        )
        .select_from(StoreInventory)
        .where(StoreInventory.store_id == store.id)
    ).one()

    pickup_rows = db.scalars(
        select(StoreOrder)
        .options(
            selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant).selectinload(ProductVariant.product)
        )
        .where(
            StoreOrder.store_id == store.id,
            StoreOrder.channel == "click_collect",
            StoreOrder.status.in_(("Ready", "Preparing", "Pending")),
        )
        .order_by(StoreOrder.id.desc())
        .limit(8)
    ).all()

    alert_rows = db.execute(
        select(
            StoreInventory.id,
            StoreInventory.variant_id,
            Product.name,
            ProductVariant.sku,
            func.coalesce(Product.product_id, Product.sku, ""),
            func.coalesce(Category.name, "Frames"),
            qty,
            func.coalesce(ProductVariant.price, Product.selling_price, Product.price, 0),
            StoreInventory.reorder_point,
        )
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(StoreInventory.store_id == store.id, qty <= func.coalesce(StoreInventory.reorder_point, 3))
        .order_by(qty.asc())
        .limit(8)
    ).all()

    return StoreAppHomeOut(
        open_orders=int(stats.open_orders or 0),
        pickups_today=int(stats.pickups_today or 0),
        low_stock=int(inv_stats.low_stock or 0),
        sku_count=int(inv_stats.sku_count or 0),
        pickups=_order_outs(db, list(pickup_rows)),
        stock_alerts=[
            StoreAppStockOut(
                id=str(r[0]),
                variant_id=int(r[1]),
                name=r[2] or "",
                sku=r[3] or "",
                product_id=r[4] or "",
                category=r[5] or "Frames",
                count=int(r[6] or 0),
                price=float(r[7] or 0),
                low=True,
            )
            for r in alert_rows
        ],
        location=_location_out(store),
    )


@router.get("/stock", response_model=StoreAppStockListOut)
def stock(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StoreAppStockListOut:
    store = _require_store(db, principal)
    limit, offset = page
    qty = StoreInventory.on_floor + StoreInventory.backroom
    stmt = (
        select(
            StoreInventory.id,
            StoreInventory.variant_id,
            Product.name,
            ProductVariant.sku,
            func.coalesce(Product.product_id, Product.sku, ""),
            func.coalesce(Category.name, "Frames"),
            qty,
            func.coalesce(ProductVariant.price, Product.selling_price, Product.price, 0),
            func.coalesce(StoreInventory.reorder_point, 3),
        )
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(StoreInventory.store_id == store.id)
    )
    count_stmt = (
        select(func.count())
        .select_from(StoreInventory)
        .join(ProductVariant, ProductVariant.id == StoreInventory.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(StoreInventory.store_id == store.id)
    )
    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            Product.name.ilike(like),
            ProductVariant.sku.ilike(like),
            Product.sku.ilike(like),
            Product.product_id.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(stmt.order_by(Product.name.asc()).limit(limit).offset(offset)).all()
    items = [
        StoreAppStockOut(
            id=str(r[0]),
            variant_id=int(r[1]),
            name=r[2] or "",
            sku=r[3] or "",
            product_id=r[4] or "",
            category=r[5] or "Frames",
            count=int(r[6] or 0),
            price=float(r[7] or 0),
            low=int(r[6] or 0) <= int(r[8] or 3),
        )
        for r in rows
    ]
    return StoreAppStockListOut(
        items=items,
        total=int(total),
        limit=limit,
        offset=offset,
        store_id=store.id,
        store_name=store.name,
    )


@router.get("/orders", response_model=StoreAppOrderListOut)
def list_orders(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    page: tuple[int, int] = Depends(pagination),
    bucket: str | None = Query(None, description="open | closed"),
    search: str | None = Query(None, alias="q"),
) -> StoreAppOrderListOut:
    store = _require_store(db, principal)
    limit, offset = page
    stmt = (
        select(StoreOrder)
        .options(
            selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant).selectinload(ProductVariant.product)
        )
        .where(StoreOrder.store_id == store.id)
    )
    count_stmt = select(func.count()).select_from(StoreOrder).where(StoreOrder.store_id == store.id)
    if bucket == "open":
        stmt = stmt.where(StoreOrder.status.in_(OPEN_STATUSES))
        count_stmt = count_stmt.where(StoreOrder.status.in_(OPEN_STATUSES))
    elif bucket == "closed":
        stmt = stmt.where(StoreOrder.status.in_(CLOSED_STATUSES))
        count_stmt = count_stmt.where(StoreOrder.status.in_(CLOSED_STATUSES))
    if search and search.strip():
        like = f"%{search.strip()}%"
        digits = digits_phone(search)
        filt = or_(
            StoreOrder.order_number.ilike(like),
            StoreOrder.customer_name.ilike(like),
            StoreOrder.customer_phone.ilike(f"%{digits}%") if digits else StoreOrder.customer_phone.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(StoreOrder.id.desc()).limit(limit).offset(offset)).all()
    return StoreAppOrderListOut(
        items=_order_outs(db, list(rows)),
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.get("/orders/{order_ref}", response_model=StoreAppOrderOut)
def get_order(
    order_ref: str,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOrderOut:
    store = _require_store(db, principal)
    return _order_outs(db, [_load_store_order(db, store.id, order_ref)])[0]


@router.post("/orders/{order_ref}/pickup-otp", response_model=StoreAppOtpResponse)
def send_order_pickup_otp(
    order_ref: str,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOtpResponse:
    store = _require_store(db, principal)
    order = _load_store_order(db, store.id, order_ref)
    message, expires, debug = send_pickup_otp(db, order)
    return StoreAppOtpResponse(
        message=message,
        expires_in_seconds=expires,
        debug_otp=debug,
    )


@router.get("/customers/{phone}", response_model=StoreAppCustomerOut)
def lookup_customer(
    phone: str,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppCustomerOut:
    p = _phone10(phone)
    customer = db.scalar(select(Customer).where(Customer.phone == p, Customer.is_active.is_(True)))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return _customer_out(db, customer, p)


@router.post("/customers/otp", response_model=StoreAppOtpResponse)
def request_otp(
    body: StoreAppOtpRequest,
    db: Session = Depends(get_db),
    _: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOtpResponse:
    p = _phone10(body.phone)
    _get_or_create_customer(db, p)

    now = ist_now()
    code = f"{secrets.randbelow(1_000_000):06d}"
    otp = OtpCode(
        phone=p,
        code=code,
        purpose=OTP_PURPOSE,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempt_count=0,
    )
    db.add(otp)
    db.flush()
    try:
        send_whatsapp_otp(p, code)
    except WhatsAppOtpError:
        if IS_PRODUCTION:
            db.rollback()
            raise HTTPException(status_code=502, detail="Failed to send OTP. Try again.")
    db.commit()
    return StoreAppOtpResponse(
        message="OTP sent",
        expires_in_seconds=OTP_EXPIRY_MINUTES * 60,
        debug_otp=None if IS_PRODUCTION else code,
    )


@router.post("/customers/verify", response_model=StoreAppCustomerOut)
def verify_otp(
    body: StoreAppOtpVerify,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppCustomerOut:
    p = _phone10(body.phone)
    now = ist_now()
    otp = db.scalar(
        select(OtpCode)
        .where(
            OtpCode.phone == p,
            OtpCode.purpose == OTP_PURPOSE,
            OtpCode.consumed_at.is_(None),
            OtpCode.expires_at > now,
        )
        .order_by(OtpCode.created_at.desc())
    )
    if not otp or otp.code != (body.otp or "").strip():
        raise HTTPException(status_code=401, detail="Invalid OTP")
    otp.consumed_at = now
    name = " ".join((body.name or "").split())
    if name:
        customer = _get_or_create_customer(db, p)
        if not has_real_name(customer.name):
            customer.name = name
    db.commit()
    return lookup_customer(p, db, principal)


def _list_price(variant: ProductVariant) -> Decimal | float:
    if variant.price is not None:
        return variant.price
    product = variant.product
    return (product.selling_price or product.price or 0) if product else 0


def _lens_price(db: Session, fit: dict | None) -> Decimal:
    if not fit or fit.get("powerMode") == "frame_only":
        return Decimal("0")
    name = str(fit.get("lensType") or "").strip()
    lens = db.scalar(select(LensType).where(func.lower(LensType.name) == name.lower()).limit(1))
    if lens is None:
        raise HTTPException(status_code=400, detail=f"Unknown lens: {name}")
    return Decimal(str(lens.price or 0))


def _take_one_from_stock(db: Session, inventory_id: int) -> None:
    qty_expr = StoreInventory.on_floor + StoreInventory.backroom
    depleted = db.execute(
        update(StoreInventory)
        .where(
            StoreInventory.id == inventory_id,
            or_(StoreInventory.on_hand >= 1, qty_expr >= 1),
        )
        .values(
            on_floor=case(
                (StoreInventory.on_floor >= 1, StoreInventory.on_floor - 1),
                else_=StoreInventory.on_floor,
            ),
            backroom=case(
                (StoreInventory.on_floor >= 1, StoreInventory.backroom),
                (StoreInventory.backroom >= 1, StoreInventory.backroom - 1),
                else_=StoreInventory.backroom,
            ),
            on_hand=case(
                (StoreInventory.on_hand >= 1, StoreInventory.on_hand - 1),
                else_=func.greatest(qty_expr - 1, 0),
            ),
        )
    )
    if depleted.rowcount != 1:
        raise HTTPException(status_code=400, detail="Insufficient stock for this product")


@router.post("/orders", response_model=StoreAppOrderOut, status_code=status.HTTP_201_CREATED)
def place_order(
    body: StoreAppPlaceOrderRequest,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOrderOut:
    store = _require_store(db, principal)
    now = ist_now()
    created_at = None
    if body.order_date and body.order_date != now.date():
        if body.order_date > now.date():
            raise HTTPException(status_code=400, detail="Order date cannot be in the future")
        created_at = datetime.combine(body.order_date, now.timetz())
    phone = _phone10(body.customer_phone)
    customer = db.scalar(select(Customer).where(Customer.phone == phone, Customer.is_active.is_(True)))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found — verify OTP first")
    # The order lands in the customer's website account, so the customer must
    # have shared an OTP with this counter recently.
    verified = db.scalar(
        select(OtpCode.id)
        .where(
            OtpCode.phone == phone,
            OtpCode.purpose == OTP_PURPOSE,
            OtpCode.consumed_at >= now - ORDER_OTP_WINDOW,
        )
        .limit(1)
    )
    if verified is None:
        raise HTTPException(status_code=403, detail="Verify the customer's OTP before placing the order")

    raw_lines = body.items or (
        [StoreAppOrderLineIn(variant_id=body.variant_id, amount=body.amount, lens_fit=body.lens_fit)]
        if body.variant_id is not None
        else []
    )
    if not raw_lines:
        raise HTTPException(status_code=400, detail="Add at least one product")
    variant_ids = {line.variant_id for line in raw_lines}
    variants = {
        v.id: v
        for v in db.scalars(
            select(ProductVariant)
            .options(selectinload(ProductVariant.product))
            .where(ProductVariant.id.in_(variant_ids))
        )
    }
    inventory = {
        inv.variant_id: inv
        for inv in db.scalars(
            select(StoreInventory).where(
                StoreInventory.store_id == store.id,
                StoreInventory.variant_id.in_(variant_ids),
            )
        )
    }
    lines: list[tuple[ProductVariant, Decimal, dict | None]] = []
    for raw in raw_lines:
        variant = variants.get(raw.variant_id)
        if not variant:
            raise HTTPException(status_code=404, detail="Product not found")
        fit = sanitize_lens_fit(raw.lens_fit, customer.id) if raw.lens_fit is not None else None
        price = Decimal(str(_list_price(variant))) + _lens_price(db, fit)
        lines.append((variant, price, fit))
    for variant_id in variant_ids:
        inv = inventory.get(variant_id)
        wanted = sum(1 for v, _, _ in lines if v.id == variant_id)
        on_hand = int((inv.on_hand if inv and inv.on_hand else 0) or 0)
        if inv and on_hand < wanted:
            on_hand = max(on_hand, int(inv.on_floor or 0) + int(inv.backroom or 0))
        if not inv or on_hand < wanted:
            name = variants[variant_id].product.name if variants[variant_id].product else "this product"
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {name}")

    pay = (body.payment or "cod").lower()
    if pay == "cod":
        pay = "cash"
    if pay not in ("card", "upi", "cash", "online"):
        pay = "cash"
    channel = "home_delivery" if body.fulfillment == "home_delivery" else "click_collect"
    power_text = (body.power or "").strip()
    fits = [fit for _, _, fit in lines]
    has_fit = any(fits)
    for fit in fits:
        if fit:
            upsert_from_lens_fit(db, customer.id, fit)
    if has_fit:
        notes = store_order_notes(fits)
    elif len(lines) == 1 and body.prescription and isinstance(body.prescription, dict):
        right = body.prescription.get("right") or {}
        left = body.prescription.get("left") or {}
        if not isinstance(right, dict):
            right = {}
        if not isinstance(left, dict):
            left = {}
        saved = upsert_for_customer(
            db,
            customer.id,
            CustomerPrescriptionUpsert(
                power_mode=(body.power_mode or "powered"),
                vision_type=(body.vision_type or "single_vision"),
                lens_type=(body.lens_type or "").strip() or None,
                right=EyeRxIn(
                    sph=str(right.get("sph") or ""),
                    cyl=str(right.get("cyl") or ""),
                    axis=str(right.get("axis") or ""),
                    pd=str(right.get("pd") or ""),
                    add=str(right.get("add") or ""),
                ),
                left=EyeRxIn(
                    sph=str(left.get("sph") or ""),
                    cyl=str(left.get("cyl") or ""),
                    axis=str(left.get("axis") or ""),
                    pd=str(left.get("pd") or ""),
                    add=str(left.get("add") or ""),
                ),
            ),
        )
        power_text = summary_for(saved) or power_text
    if not has_fit:
        notes = " · ".join(p for p in [(body.lens_type or "").strip(), power_text] if p)[:500] or None
    total = sum((price for _, price, _ in lines), Decimal("0"))

    order_number = f"SA-{ist_now().strftime('%y%m%d')}-{secrets.randbelow(9000) + 1000}"

    user = db.get(User, principal.sub)
    pickup_at = ist_now() + timedelta(days=3) if channel == "click_collect" else None
    order = StoreOrder(
        order_number=order_number,
        store_id=store.id,
        customer_name=customer.name or f"Customer {phone[-4:]}",
        customer_phone=phone,
        customer_id=customer.id,
        channel=channel,
        payment_method=pay,
        associate_name=user.name if user else "Store Manager",
        notes=notes,
        subtotal=total,
        tax=Decimal("0"),
        total=total,
        status="Pending",
        pickup_at=pickup_at,
    )
    if created_at:
        order.created_at = created_at
    db.add(order)
    db.flush()
    for variant, price, fit in lines:
        db.add(
            StoreOrderItem(
                store_order_id=order.id,
                variant_id=variant.id,
                qty=1,
                price_snapshot=price,
                lens_fit=fit,
            )
        )
        _take_one_from_stock(db, inventory[variant.id].id)
    db.commit()
    db.refresh(order)
    order = db.scalar(
        select(StoreOrder)
        .options(
            selectinload(StoreOrder.store),
            selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant).selectinload(ProductVariant.product),
        )
        .where(StoreOrder.id == order.id)
    )
    send_store_order_placed(order, store_invoice_token(order))
    return _order_outs(db, [order])[0]


@router.patch("/orders/{order_ref}/status", response_model=StoreAppOrderOut)
def patch_status(
    order_ref: str,
    body: StoreAppStatusPatch,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOrderOut:
    store = _require_store(db, principal)
    order = _load_store_order(db, store.id, order_ref)
    mapped = APP_TO_STATUS.get(body.status) or body.status
    if mapped in ("Preparing", "Ready") and any(is_power_later(f) for _, f in store_item_fits(order)):
        raise HTTPException(status_code=409, detail="Add the customer's power before sending this order to the lab.")
    if mapped == "Collected" and (order.channel or "") == "click_collect":
        consume_pickup_otp(db, order, body.otp or "")
    previous_status = order.status
    order.status = mapped
    db.commit()
    # Re-load with item/variant/product eager options — refresh() alone can
    # leave relationships expired and trigger lazy loads in _frame_name.
    reloaded = _load_store_order(db, store.id, order.order_number)
    notify_store_order_status(reloaded, previous_status, invoice_token_for(db, reloaded))
    return _order_outs(db, [reloaded])[0]


@router.patch("/orders/{order_ref}/lens-fit", response_model=StoreAppOrderOut)
def add_order_power(
    order_ref: str,
    body: StoreAppLensFitPatch,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOrderOut:
    """Attach power to a counter order placed with "power to follow"."""
    store = _require_store(db, principal)
    order = _load_store_order(db, store.id, order_ref)
    fits = store_item_fits(order)
    target = next(
        (
            (item, fit)
            for item, fit in fits
            if is_power_later(fit) and (body.item_id is None or item.id == body.item_id)
        ),
        None,
    )
    if target is None:
        raise HTTPException(status_code=409, detail="Power is already on file for this order.")
    line, current = target
    if order.status not in OPEN_STATUSES:
        raise HTTPException(status_code=409, detail="This order is already closed.")
    if order.customer_id is None:
        raise HTTPException(status_code=409, detail="This order has no linked customer.")
    incoming = body.lens_fit if isinstance(body.lens_fit, dict) else {}
    if str(incoming.get("source") or "").lower() == "later":
        raise HTTPException(status_code=422, detail="Add the power or upload the prescription.")
    fit = sanitize_lens_fit(
        {
            **incoming,
            "powerMode": current.get("powerMode"),
            "lensType": current.get("lensType"),
            "patient": incoming.get("patient") or current.get("patient"),
        },
        order.customer_id,
    )
    line.lens_fit = fit
    if order.lens_fit and fits and fits[0][0].id == line.id:
        order.lens_fit = fit
    order.notes = store_order_notes([fit if i.id == line.id else f for i, f in fits])
    upsert_from_lens_fit(db, order.customer_id, fit)
    db.commit()
    return _order_outs(db, [_load_store_order(db, store.id, order.order_number)])[0]


@router.get("/lens-types", response_model=list[StoreAppLensTypeOut])
def lens_types(db: Session = Depends(get_db)) -> list[StoreAppLensTypeOut]:
    rows = db.scalars(select(LensType).order_by(LensType.id.asc())).all()
    return [
        StoreAppLensTypeOut(
            id=r.id,
            name=r.name,
            description=r.description or "",
            price=float(r.price or 0),
        )
        for r in rows
    ]


@router.post("/customers/{phone}/prescription/presign", response_model=ImagePresignResponse)
def presign_customer_prescription(
    phone: str,
    payload: ImagePresignRequest,
    db: Session = Depends(get_db),
) -> ImagePresignResponse:
    p = _phone10(phone)
    customer = db.scalar(select(Customer).where(Customer.phone == p, Customer.is_active.is_(True)))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    uploads = presign_prescription_puts(customer.id, [(f.filename, f.content_type) for f in payload.files])
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )
