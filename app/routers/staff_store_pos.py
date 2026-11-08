"""Staff store POS — /staff/store/pos.

Counter sales come straight from warehouse stock; stores hold none of their own.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.offer_pricing import price_for_offer, winning_offers_for
from app.core.order_reservation import available_by_variant, available_qty_expr, take_variant
from app.core.order_service import next_order_number
from app.core.staff_users import digits_phone
from app.core.store_order_customer import store_invoice_token, store_order_eager
from app.core.whatsapp_orders import send_store_order_placed
from app.database import get_db
from app.deps import require_role, TokenPrincipal
from app.dto.store_order_dto import (
    PosCatalogItemOut,
    PosCatalogResponse,
    PosCheckoutOut,
    PosCheckoutRequest,
)
from app.schemas import (
    Category,
    Product,
    ProductVariant,
    Store,
    StoreOrder,
    StoreOrderItem,
    User,
)

router = APIRouter(prefix="/staff/store/pos", tags=["staff-store-pos"], dependencies=[Depends(require_role("store_manager"))])


def _default_store(db: Session) -> Store | None:
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


def _resolve_store(db: Session, principal: TokenPrincipal, store_id: int | None) -> Store | None:
    sid = principal.store_id or store_id
    if sid is not None:
        return db.get(Store, sid)
    return _default_store(db)


@router.get("/catalog", response_model=PosCatalogResponse)
def pos_catalog(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
    store_id: int | None = None,
    search: str | None = Query(None, alias="q"),
) -> PosCatalogResponse:
    store = _resolve_store(db, principal, store_id)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")

    stock_expr = available_qty_expr(ProductVariant.id)
    cat_expr = func.coalesce(Category.name, "General")
    price_expr = func.coalesce(ProductVariant.price, Product.price)
    stmt = (
        select(ProductVariant, Product.name, cat_expr, price_expr, stock_expr)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(func.lower(func.coalesce(Product.status, "active")) != "inactive")
        .order_by(stock_expr.desc(), ProductVariant.id.asc())
        .limit(200)
    )
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                ProductVariant.sku.ilike(like),
                Product.name.ilike(like),
                Product.sku.ilike(like),
            )
        )
    rows = db.execute(stmt).all()

    items = [
        PosCatalogItemOut(
            id=str(variant.id),
            name=name or variant.sku,
            sku=variant.sku or "",
            price=float(price or 0),
            category=category or "General",
            stock=max(0, int(stock or 0)),
            variant_id=variant.id,
        )
        for variant, name, category, price, stock in rows
    ]
    return PosCatalogResponse(
        items=items, store_id=store.id, store_name=store.name or ""
    )


@router.post("/checkout", response_model=PosCheckoutOut, status_code=status.HTTP_201_CREATED)
def pos_checkout(
    body: PosCheckoutRequest,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> PosCheckoutOut:
    if not body.items:
        raise HTTPException(status_code=422, detail="Cart is empty")

    phone = digits_phone(body.customer_phone)
    if len(phone) == 12 and phone.startswith("91"):
        phone = phone[2:]
    if phone and len(phone) != 10:
        raise HTTPException(status_code=400, detail="Enter a valid 10-digit phone number")

    store = _resolve_store(db, principal, body.store_id)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")

    # Aggregate qty by variant
    qty_by_variant: dict[int, int] = {}
    for line in body.items:
        if line.qty <= 0:
            continue
        qty_by_variant[line.variant_id] = qty_by_variant.get(line.variant_id, 0) + line.qty
    if not qty_by_variant:
        raise HTTPException(status_code=422, detail="Cart is empty")

    variant_ids = list(qty_by_variant.keys())
    variants = {
        v.id: v
        for v in db.scalars(
            select(ProductVariant)
            .where(ProductVariant.id.in_(variant_ids))
            .options(selectinload(ProductVariant.product))
        ).all()
    }
    if len(variants) != len(variant_ids):
        raise HTTPException(status_code=404, detail="One or more variants not found")

    available = available_by_variant(db, variant_ids)

    line_prices: list[tuple[int, int, Decimal]] = []
    subtotal = Decimal("0")
    products = list({variant.product.id: variant.product for variant in variants.values()}.values())
    winning_offers = winning_offers_for(db, products)
    for vid, qty in qty_by_variant.items():
        left = available.get(vid, 0)
        if left < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Only {left} of {variants[vid].sku} left in the warehouse",
            )
        variant = variants[vid]
        price = Decimal(
            str(
                variant.price
                if variant.price is not None
                else variant.product.selling_price or variant.product.price
            )
        )
        winner = winning_offers.get(variant.product.id)
        if winner is not None:
            price = price_for_offer(winner, variant.product, base_price=price).final_price
        subtotal += price * qty
        line_prices.append((vid, qty, price))

    # Prices already include GST; invoices split it out using the admin GST settings.
    tax = Decimal("0")
    total = subtotal + tax

    pay = (body.payment_method or "card").lower()
    if pay not in ("card", "upi", "cash", "online"):
        pay = "card"

    order_number = next_order_number(db)

    user = db.get(User, principal.sub)

    order = StoreOrder(
        order_number=order_number,
        store_id=store.id,
        customer_name=(body.customer_name or "").strip() or f"Walk-in #{order_number[-4:]}",
        customer_phone=phone or None,
        channel="in_store",
        payment_method=pay,
        associate_name=body.associate_name or (user.name if user else "Store Associate"),
        subtotal=subtotal,
        tax=tax,
        total=total,
        status="Completed",
    )
    db.add(order)
    db.flush()

    db.add_all(
        [
            StoreOrderItem(
                store_order_id=order.id,
                variant_id=vid,
                qty=qty,
                price_snapshot=price,
            )
            for vid, qty, price in line_prices
        ]
    )

    for vid, qty, _ in line_prices:
        if take_variant(db, vid, qty) < qty:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"{variants[vid].sku} just sold out in the warehouse. Refresh and try again.",
            )

    db.commit()

    sent = False
    if phone:
        billed = db.scalar(
            select(StoreOrder).where(StoreOrder.id == order.id).options(*store_order_eager())
        )
        sent = send_store_order_placed(billed, store_invoice_token(billed))
    message = f"Payment collected · Bill #{order.order_number}"
    if phone:
        message += " · Bill sent on WhatsApp" if sent else " · WhatsApp bill could not be sent"
    return PosCheckoutOut(
        id=order.order_number,
        total=float(total),
        subtotal=float(subtotal),
        tax=float(tax),
        status=order.status,
        message=message,
    )
