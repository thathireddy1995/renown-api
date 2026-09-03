"""Store manager tablet APIs — /store/app.

Lambda-friendly: batched joins, no per-row queries. Auth is the existing
store_manager JWT from POST /staff/auth/login.
"""

from __future__ import annotations

import secrets
from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import IS_PRODUCTION, OTP_EXPIRY_MINUTES
from app.core.customer_prescription import (
    get_for_customer,
    summary_for,
    to_out,
    upsert_for_customer,
)
from app.core.ist import now as ist_now
from app.core.staff_users import digits_phone
from app.core.whatsapp_otp import WhatsAppOtpError, send_whatsapp_otp
from app.database import get_db
from app.deps import pagination, require_role, TokenPrincipal
from app.dto.prescription_dto import CustomerPrescriptionUpsert, EyeRxIn
from app.dto.store_app_dto import (
    StoreAppCustomerOut,
    StoreAppHomeOut,
    StoreAppLocationOut,
    StoreAppMeOut,
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


def _frame_name(order: StoreOrder) -> str:
    if not order.items:
        return "—"
    item = order.items[0]
    variant = item.variant
    if variant is None:
        return "—"
    product = variant.product
    return product.name if product is not None else (variant.sku or "—")


def _order_out(order: StoreOrder) -> StoreAppOrderOut:
    notes = (order.notes or "").strip()
    lens = ""
    power = ""
    if " · " in notes:
        lens, _, power = notes.partition(" · ")
    elif notes:
        lens = notes
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
    )


def _get_or_create_customer(db: Session, phone: str) -> Customer:
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if customer:
        if not customer.is_active:
            customer.is_active = True
        return customer
    customer = Customer(phone=phone, name=f"Customer {phone[-4:]}", is_active=True)
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
            func.coalesce(ProductVariant.price, Product.price, 0),
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
        pickups=[_order_out(o) for o in pickup_rows],
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
            func.coalesce(ProductVariant.price, Product.price, 0),
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
        items=[_order_out(o) for o in rows],
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
    stmt = (
        select(StoreOrder)
        .options(
            selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant).selectinload(ProductVariant.product)
        )
        .where(StoreOrder.store_id == store.id)
    )
    order = db.scalar(stmt.where(StoreOrder.order_number == order_ref))
    if not order and order_ref.isdigit():
        order = db.scalar(stmt.where(StoreOrder.id == int(order_ref)))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_out(order)


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
    db.commit()
    return lookup_customer(p, db, principal)


@router.post("/orders", response_model=StoreAppOrderOut, status_code=status.HTTP_201_CREATED)
def place_order(
    body: StoreAppPlaceOrderRequest,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOrderOut:
    store = _require_store(db, principal)
    phone = _phone10(body.customer_phone)
    customer = db.scalar(select(Customer).where(Customer.phone == phone, Customer.is_active.is_(True)))
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found — verify OTP first")

    variant = db.scalar(
        select(ProductVariant)
        .options(selectinload(ProductVariant.product))
        .where(ProductVariant.id == body.variant_id)
    )
    if not variant:
        raise HTTPException(status_code=404, detail="Frame not found")

    inv = db.scalar(
        select(StoreInventory).where(
            StoreInventory.store_id == store.id,
            StoreInventory.variant_id == variant.id,
        )
    )
    on_hand = int((inv.on_hand if inv and inv.on_hand else 0) or 0)
    if inv and on_hand < 1:
        on_hand = int(inv.on_floor or 0) + int(inv.backroom or 0)
    if not inv or on_hand < 1:
        raise HTTPException(status_code=400, detail="Insufficient stock for this frame")

    price = Decimal(
        str(
            body.amount
            if body.amount
            else (variant.price if variant.price is not None else variant.product.selling_price or variant.product.price or 0)
        )
    )
    pay = (body.payment or "cod").lower()
    if pay == "cod":
        pay = "cash"
    if pay not in ("card", "upi", "cash", "online"):
        pay = "cash"
    channel = "home_delivery" if body.fulfillment == "home_delivery" else "click_collect"
    power_text = (body.power or "").strip()
    if body.prescription and isinstance(body.prescription, dict):
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
    notes = " · ".join(p for p in [(body.lens_type or "").strip(), power_text] if p)

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
        notes=notes or None,
        subtotal=price,
        tax=Decimal("0"),
        total=price,
        status="Pending",
        pickup_at=pickup_at,
    )
    db.add(order)
    db.flush()
    db.add(
        StoreOrderItem(
            store_order_id=order.id,
            variant_id=variant.id,
            qty=1,
            price_snapshot=price,
        )
    )

    qty_expr = StoreInventory.on_floor + StoreInventory.backroom
    depleted = db.execute(
        update(StoreInventory)
        .where(
            StoreInventory.id == inv.id,
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
        raise HTTPException(status_code=400, detail="Insufficient stock for this frame")
    db.commit()
    db.refresh(order)
    order = db.scalar(
        select(StoreOrder)
        .options(
            selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant).selectinload(ProductVariant.product)
        )
        .where(StoreOrder.id == order.id)
    )
    return _order_out(order)


@router.patch("/orders/{order_ref}/status", response_model=StoreAppOrderOut)
def patch_status(
    order_ref: str,
    body: StoreAppStatusPatch,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StoreAppOrderOut:
    store = _require_store(db, principal)
    stmt = (
        select(StoreOrder)
        .options(
            selectinload(StoreOrder.items).selectinload(StoreOrderItem.variant).selectinload(ProductVariant.product)
        )
        .where(StoreOrder.store_id == store.id)
    )
    order = db.scalar(stmt.where(StoreOrder.order_number == order_ref))
    if not order and order_ref.isdigit():
        order = db.scalar(stmt.where(StoreOrder.id == int(order_ref)))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    mapped = APP_TO_STATUS.get(body.status) or body.status
    order.status = mapped
    db.commit()
    db.refresh(order)
    return _order_out(order)
