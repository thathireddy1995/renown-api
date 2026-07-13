"""Customer addresses — /customer/addresses (JWT required)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_customer
from app.dto.order_dto import (
    AddressCreate,
    AddressListResponse,
    AddressOut,
    AddressUpdate,
)
from app.schemas import Address, Customer

router = APIRouter(prefix="/customer/addresses", tags=["customer-addresses"])


def _out(row: Address) -> AddressOut:
    return AddressOut(
        id=str(row.id),
        name=row.label or "Address",
        line1=row.line1,
        line2=row.line2,
        city=row.city or "",
        zip=row.postal_code or "",
        phone=row.phone or "",
        state=row.state,
        country=row.country,
        is_default=row.is_default,
    )


def _label(payload: AddressCreate | AddressUpdate) -> str | None:
    data = payload.model_dump(exclude_unset=True)
    return data.get("name") or data.get("label")


def _postal(payload: AddressCreate | AddressUpdate) -> str | None:
    data = payload.model_dump(exclude_unset=True)
    return data.get("zip") if "zip" in data else data.get("postal_code")


@router.get("/", response_model=AddressListResponse)
def list_addresses(
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> AddressListResponse:
    rows = db.scalars(
        select(Address)
        .where(Address.customer_id == customer.id)
        .order_by(Address.is_default.desc(), Address.id.asc())
    ).all()
    return AddressListResponse(items=[_out(r) for r in rows])


@router.post("/", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(
    payload: AddressCreate,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> AddressOut:
    if payload.is_default:
        for row in db.scalars(
            select(Address).where(Address.customer_id == customer.id)
        ).all():
            row.is_default = False

    row = Address(
        customer_id=customer.id,
        label=_label(payload) or "Home",
        line1=payload.line1,
        line2=payload.line2,
        city=payload.city,
        state=payload.state,
        postal_code=_postal(payload) or payload.postal_code,
        country=payload.country or "India",
        phone=payload.phone,
        is_default=payload.is_default,
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _out(row)


@router.patch("/{address_id}", response_model=AddressOut)
def update_address(
    address_id: int,
    payload: AddressUpdate,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> AddressOut:
    row = db.scalar(
        select(Address).where(
            Address.id == address_id, Address.customer_id == customer.id
        )
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found.")

    data = payload.model_dump(exclude_unset=True)
    if "name" in data or "label" in data:
        row.label = data.get("name") or data.get("label") or row.label
    if "line1" in data and data["line1"] is not None:
        row.line1 = data["line1"]
    if "line2" in data:
        row.line2 = data["line2"]
    if "city" in data:
        row.city = data["city"]
    if "state" in data:
        row.state = data["state"]
    if "zip" in data or "postal_code" in data:
        row.postal_code = data.get("zip") if "zip" in data else data.get("postal_code")
    if "country" in data:
        row.country = data["country"]
    if "phone" in data:
        row.phone = data["phone"]
    if data.get("is_default") is True:
        for other in db.scalars(
            select(Address).where(Address.customer_id == customer.id)
        ).all():
            other.is_default = False
        row.is_default = True
    elif data.get("is_default") is False:
        row.is_default = False

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _out(row)


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    row = db.scalar(
        select(Address).where(
            Address.id == address_id, Address.customer_id == customer.id
        )
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Address not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
