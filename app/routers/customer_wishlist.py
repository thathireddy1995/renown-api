"""Customer wishlist — /customer/wishlist (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.product_resolve import public_product_id, resolve_product
from app.database import get_db
from app.deps import get_current_customer
from app.dto.cart_dto import WishlistAddRequest, WishlistItemOut, WishlistListResponse
from app.schemas import Customer, Product, WishlistItem

router = APIRouter(prefix="/customer/wishlist", tags=["customer-wishlist"])

_LOAD = (selectinload(WishlistItem.product).selectinload(Product.images),)


def _out(item: WishlistItem) -> WishlistItemOut:
    return WishlistItemOut(id=item.id, productId=public_product_id(item.product))


@router.get("/", response_model=WishlistListResponse)
def get_wishlist(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> WishlistListResponse:
    rows = db.scalars(
        select(WishlistItem)
        .where(WishlistItem.customer_id == customer.id)
        .options(*_LOAD)
        .order_by(WishlistItem.id.asc())
    ).all()
    return WishlistListResponse(items=[_out(r) for r in rows])


@router.post("/", response_model=WishlistItemOut, status_code=status.HTTP_201_CREATED)
def add_wishlist(
    payload: WishlistAddRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> WishlistItemOut:
    product = resolve_product(db, payload.product_id)
    existing = db.scalar(
        select(WishlistItem).where(
            WishlistItem.customer_id == customer.id,
            WishlistItem.product_id == product.id,
        )
    )
    if existing:
        item = db.scalar(
            select(WishlistItem).where(WishlistItem.id == existing.id).options(*_LOAD)
        )
        assert item is not None
        return _out(item)

    item = WishlistItem(customer_id=customer.id, product_id=product.id)
    db.add(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    item = db.scalar(
        select(WishlistItem).where(WishlistItem.id == item.id).options(*_LOAD)
    )
    assert item is not None
    return _out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wishlist_item(
    item_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    item = db.scalar(
        select(WishlistItem).where(
            WishlistItem.id == item_id, WishlistItem.customer_id == customer.id
        )
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist item not found."
        )
    db.delete(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.delete("/by-product/{product_ref}", status_code=status.HTTP_204_NO_CONTENT)
def delete_wishlist_by_product(
    product_ref: str,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    product = resolve_product(db, product_ref)
    item = db.scalar(
        select(WishlistItem).where(
            WishlistItem.customer_id == customer.id,
            WishlistItem.product_id == product.id,
        )
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Wishlist item not found."
        )
    db.delete(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
