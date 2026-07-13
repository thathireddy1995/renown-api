"""Customer compare — /customer/compare (JWT required, max 4 items)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.product_resolve import public_product_id, resolve_product
from app.database import get_db
from app.deps import get_current_customer
from app.dto.cart_dto import CompareAddRequest, CompareItemOut, CompareListResponse
from app.schemas import CompareItem, Customer, Product

router = APIRouter(prefix="/customer/compare", tags=["customer-compare"])

COMPARE_CAP = 4
_LOAD = (selectinload(CompareItem.product).selectinload(Product.images),)


def _out(item: CompareItem) -> CompareItemOut:
    return CompareItemOut(id=item.id, productId=public_product_id(item.product))


@router.get("/", response_model=CompareListResponse)
def get_compare(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CompareListResponse:
    rows = db.scalars(
        select(CompareItem)
        .where(CompareItem.customer_id == customer.id)
        .options(*_LOAD)
        .order_by(CompareItem.id.asc())
    ).all()
    return CompareListResponse(items=[_out(r) for r in rows])


@router.post("/", response_model=CompareItemOut, status_code=status.HTTP_201_CREATED)
def add_compare(
    payload: CompareAddRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CompareItemOut:
    product = resolve_product(db, payload.product_id)
    existing = db.scalar(
        select(CompareItem).where(
            CompareItem.customer_id == customer.id,
            CompareItem.product_id == product.id,
        )
    )
    if existing:
        item = db.scalar(
            select(CompareItem).where(CompareItem.id == existing.id).options(*_LOAD)
        )
        assert item is not None
        return _out(item)

    count = db.scalar(
        select(func.count())
        .select_from(CompareItem)
        .where(CompareItem.customer_id == customer.id)
    ) or 0
    if count >= COMPARE_CAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Compare list is limited to {COMPARE_CAP} items.",
        )

    item = CompareItem(customer_id=customer.id, product_id=product.id)
    db.add(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    item = db.scalar(
        select(CompareItem).where(CompareItem.id == item.id).options(*_LOAD)
    )
    assert item is not None
    return _out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_compare_item(
    item_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    item = db.scalar(
        select(CompareItem).where(
            CompareItem.id == item_id, CompareItem.customer_id == customer.id
        )
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compare item not found."
        )
    db.delete(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.delete("/by-product/{product_ref}", status_code=status.HTTP_204_NO_CONTENT)
def delete_compare_by_product(
    product_ref: str,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    product = resolve_product(db, product_ref)
    item = db.scalar(
        select(CompareItem).where(
            CompareItem.customer_id == customer.id,
            CompareItem.product_id == product.id,
        )
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Compare item not found."
        )
    db.delete(item)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
