"""Customer cart — /customer/cart (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.product_resolve import public_product_id, resolve_product
from app.database import get_db
from app.deps import get_current_customer
from app.dto.cart_dto import (
    CartAddRequest,
    CartItemOut,
    CartListResponse,
    CartUpdateRequest,
)
from app.schemas import CartItem, Customer, Product, ProductVariant

router = APIRouter(prefix="/customer/cart", tags=["customer-cart"])

_CART_LOAD = (
    selectinload(CartItem.product).selectinload(Product.images),
    selectinload(CartItem.variant),
)


def _out(item: CartItem) -> CartItemOut:
    return CartItemOut(
        id=item.id,
        productId=public_product_id(item.product),
        qty=item.qty,
        savedForLater=item.saved_for_later,
        variantId=item.variant_id,
    )


@router.get("/", response_model=CartListResponse)
def get_cart(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CartListResponse:
    rows = db.scalars(
        select(CartItem)
        .where(CartItem.customer_id == customer.id)
        .options(*_CART_LOAD)
        .order_by(CartItem.id.asc())
    ).all()
    return CartListResponse(items=[_out(r) for r in rows])


@router.post("/", response_model=CartItemOut, status_code=status.HTTP_201_CREATED)
def add_to_cart(
    payload: CartAddRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CartItemOut:
    product = resolve_product(db, payload.product_id)
    if payload.variant_id is not None:
        variant = db.get(ProductVariant, payload.variant_id)
        if not variant or variant.product_id != product.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Variant does not belong to this product.",
            )

    existing = db.scalar(
        select(CartItem).where(
            CartItem.customer_id == customer.id,
            CartItem.product_id == product.id,
            CartItem.variant_id == payload.variant_id
            if payload.variant_id is not None
            else CartItem.variant_id.is_(None),
            CartItem.saved_for_later.is_(False),
        )
    )
    if existing:
        existing.qty += payload.qty
        item = existing
    else:
        # Also merge into a saved-for-later row for the same product/variant.
        existing_any = db.scalar(
            select(CartItem).where(
                CartItem.customer_id == customer.id,
                CartItem.product_id == product.id,
                CartItem.variant_id == payload.variant_id
                if payload.variant_id is not None
                else CartItem.variant_id.is_(None),
            )
        )
        if existing_any:
            existing_any.qty += payload.qty
            existing_any.saved_for_later = False
            item = existing_any
        else:
            item = CartItem(
                customer_id=customer.id,
                product_id=product.id,
                variant_id=payload.variant_id,
                qty=payload.qty,
                saved_for_later=False,
            )
            db.add(item)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    item = db.scalar(
        select(CartItem).where(CartItem.id == item.id).options(*_CART_LOAD)
    )
    assert item is not None
    return _out(item)


@router.patch("/{item_id}", response_model=CartItemOut)
def update_cart_item(
    item_id: int,
    payload: CartUpdateRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CartItemOut:
    item = db.scalar(
        select(CartItem)
        .where(CartItem.id == item_id, CartItem.customer_id == customer.id)
        .options(*_CART_LOAD)
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")

    data = payload.model_dump(exclude_unset=True)
    if "qty" in data and data["qty"] is not None:
        item.qty = data["qty"]
    if "saved_for_later" in data and data["saved_for_later"] is not None:
        item.saved_for_later = data["saved_for_later"]

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    item = db.scalar(
        select(CartItem).where(CartItem.id == item_id).options(*_CART_LOAD)
    )
    assert item is not None
    return _out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    item = db.scalar(
        select(CartItem).where(CartItem.id == item_id, CartItem.customer_id == customer.id)
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found.")
    db.delete(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
