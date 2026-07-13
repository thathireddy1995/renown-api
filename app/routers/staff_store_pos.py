"""Staff store POS — /staff/store/pos."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_store_staff
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
    StoreInventory,
    StoreOrder,
    StoreOrderItem,
    User,
)

router = APIRouter(prefix="/staff/store/pos", tags=["staff-store-pos"])


def _default_store(db: Session) -> Store | None:
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


@router.get("/catalog", response_model=PosCatalogResponse)
def pos_catalog(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_store_staff),
    store_id: int | None = None,
    search: str | None = Query(None, alias="q"),
) -> PosCatalogResponse:
    store = db.get(Store, store_id) if store_id else _default_store(db)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")

    stock_expr = func.coalesce(StoreInventory.on_hand, 0)
    cat_expr = func.coalesce(Category.name, "General")
    price_expr = func.coalesce(ProductVariant.price, Product.price)

    stmt = (
        select(
            ProductVariant,
            Product.name,
            cat_expr,
            price_expr,
            stock_expr,
        )
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .outerjoin(
            StoreInventory,
            (StoreInventory.variant_id == ProductVariant.id)
            & (StoreInventory.store_id == store.id),
        )
        .where(Product.status == "active")
        .order_by(ProductVariant.id.asc())
        .limit(100)
    )
    if search and search.strip():
        like = f"%{search.strip()}%"
        from sqlalchemy import or_

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
            sku=variant.sku,
            price=float(price or 0),
            category=category or "General",
            stock=int(stock or 0),
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
    user: User = Depends(get_current_store_staff),
) -> PosCheckoutOut:
    if not body.items:
        raise HTTPException(status_code=422, detail="Cart is empty")

    store = db.get(Store, body.store_id) if body.store_id else _default_store(db)
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

    inv_rows = {
        r.variant_id: r
        for r in db.scalars(
            select(StoreInventory).where(
                StoreInventory.store_id == store.id,
                StoreInventory.variant_id.in_(variant_ids),
            )
        ).all()
    }

    line_prices: list[tuple[int, int, Decimal]] = []
    subtotal = Decimal("0")
    for vid, qty in qty_by_variant.items():
        inv = inv_rows.get(vid)
        on_hand = int(inv.on_hand or 0) if inv else 0
        if on_hand < qty:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {variants[vid].sku}",
            )
        variant = variants[vid]
        price = Decimal(str(variant.price if variant.price is not None else variant.product.price))
        subtotal += price * qty
        line_prices.append((vid, qty, price))

    tax = (subtotal * Decimal("0.18")).quantize(Decimal("1"))
    total = subtotal + tax

    pay = (body.payment_method or "card").lower()
    if pay not in ("card", "upi", "cash", "online"):
        pay = "card"

    order_number = f"SO-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    while db.scalar(select(StoreOrder.id).where(StoreOrder.order_number == order_number)):
        order_number = f"SO-{int(datetime.now(timezone.utc).timestamp()) % 100000 + 1}"

    order = StoreOrder(
        order_number=order_number,
        store_id=store.id,
        customer_name=body.customer_name or f"Walk-in #{order_number[-4:]}",
        channel="in_store",
        payment_method=pay,
        associate_name=body.associate_name or user.name,
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

    # Bulk inventory decrement in one UPDATE with CASE expressions
    floor_cases = []
    back_cases = []
    hand_cases = []
    for vid, qty, _ in line_prices:
        inv = inv_rows[vid]
        floor = int(inv.on_floor or 0)
        back = int(inv.backroom or 0)
        take_floor = min(floor, qty)
        take_back = qty - take_floor
        new_floor = floor - take_floor
        new_back = back - take_back
        floor_cases.append((StoreInventory.variant_id == vid, new_floor))
        back_cases.append((StoreInventory.variant_id == vid, new_back))
        hand_cases.append((StoreInventory.variant_id == vid, new_floor + new_back))

    db.execute(
        update(StoreInventory)
        .where(
            StoreInventory.store_id == store.id,
            StoreInventory.variant_id.in_(variant_ids),
        )
        .values(
            on_floor=case(*floor_cases, else_=StoreInventory.on_floor),
            backroom=case(*back_cases, else_=StoreInventory.backroom),
            on_hand=case(*hand_cases, else_=StoreInventory.on_hand),
        )
    )

    db.commit()
    return PosCheckoutOut(
        id=order.order_number,
        total=float(total),
        subtotal=float(subtotal),
        tax=float(tax),
        status=order.status,
        message=f"Payment collected · Bill #{order.order_number}",
    )
