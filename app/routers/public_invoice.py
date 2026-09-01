"""Public invoice verify — /public/invoice/{token}.

Anyone with the invoice PDF can scan its QR code and confirm the invoice is
genuine. The QR encodes a random UUID token stored on the Order row.

The response is intentionally limited: no address, no phone/email, no payment
IDs. Enough for a stranger to confirm the invoice matches the seller's records
without leaking customer PII.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.ist import format_ist_date
from app.core.company_settings import seller_public
from app.database import get_db
from app.schemas import Order, OrderItem

router = APIRouter(prefix="/public/invoice", tags=["public-invoice"])


class PublicInvoiceItem(BaseModel):
    name: str
    qty: int


class PublicInvoiceSeller(BaseModel):
    trade_name: str
    gstin: str
    state: str
    city: str
    website: str


class PublicInvoiceResponse(BaseModel):
    order_number: str
    date: str
    status: str
    delivery: str
    payment_method: str
    payment_status: str
    total: float
    currency: str = "INR"
    items: list[PublicInvoiceItem] = Field(default_factory=list)
    seller: PublicInvoiceSeller
    customer_masked: str | None = None


def _mask_name(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip()
    if not name:
        return None
    first, *rest = name.split()
    initials = "".join(word[:1].upper() for word in rest if word)
    if not initials:
        return f"{first[:1].upper()}."
    return f"{first[:1].upper()}. {initials}."


@router.get("/{token}", response_model=PublicInvoiceResponse)
def verify_invoice(
    token: str,
    db: Session = Depends(get_db),
) -> PublicInvoiceResponse:
    token = (token or "").strip()
    # UUIDs are 36 chars; keep this loose enough to accept any reasonable
    # opaque token but reject obvious probes.
    if not token or len(token) < 8 or len(token) > 64:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found or link is invalid.",
        )

    order = db.scalar(
        select(Order)
        .where(Order.verify_token == token)
        .options(
            selectinload(Order.items)
            .selectinload(OrderItem.product),
            selectinload(Order.customer),
        )
    )
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found or link is invalid.",
        )

    items: list[PublicInvoiceItem] = []
    for line in order.items or []:
        name = (line.name_snapshot or "").strip()
        if not name and line.product is not None:
            name = (line.product.name or "").strip()
        items.append(PublicInvoiceItem(name=name or "Item", qty=int(line.qty or 0)))

    return PublicInvoiceResponse(
        order_number=order.order_number,
        date=format_ist_date(order.created_at),
        status=(order.status or "").title(),
        delivery=(order.delivery or "ship"),
        payment_method=order.payment_method or "",
        payment_status=order.payment_status or "",
        total=float(order.total or 0),
        items=items,
        seller=PublicInvoiceSeller(**seller_public(db)),
        customer_masked=_mask_name(order.customer.name if order.customer else None),
    )
