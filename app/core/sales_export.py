"""Sales register rows for the Tally and GSTR-1 exports (admin Cashbook).

Every figure mirrors the customer tax invoice PDF (customer-renown/src/lib/invoice.ts
and apk-renown invoice_pdf.dart): one invoice per order line numbered
``REW-<order stamp>-NN``, prices are GST-inclusive, and tax is back-calculated
from the amount paid for that line after its coupon share. Shipping and
platform fee sit on the last line. Keep the two in sync — the exports and the
invoices must show the same numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.company_settings import company_details
from app.core.gst_rates import effective_gst_percent, effective_hsn
from app.core.ist import as_ist, end_of_day, start_of_day
from app.dto.sales_export_dto import SalesExportLine, SalesExportResponse
from app.dto.settings_dto import CompanyDetailsOut
from app.schemas import Category, Order, OrderItem, Product, ProductVariant, StoreOrder, StoreOrderItem

UQC = "NOS"
ZERO = Decimal("0")
CENT = Decimal("0.01")

STORE_VOID_STATUSES = {"cancelled", "missed", "void"}
STORE_PAYMENT_LABEL = {"cash": "Cash", "card": "Card", "upi": "UPI", "online": "Online"}


def _r2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _dec(value: object) -> Decimal:
    try:
        return Decimal(str(value if value is not None else 0))
    except (ArithmeticError, ValueError):
        return ZERO


def _ddmmyyyy(dt: datetime | None) -> str:
    return as_ist(dt).strftime("%d-%m-%Y") if dt else ""


def invoice_stamp(order_number: str) -> str:
    stamp = re.sub(r"[^A-Za-z0-9_-]", "", order_number or "")[-8:].upper()
    return stamp or "INV"


def invoice_number(order_number: str, line_index: int) -> str:
    return f"REW-{invoice_stamp(order_number)}-{line_index + 1:02d}"


def _norm_place(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").strip().lower())


def is_intra_state(state: str | None, company: CompanyDetailsOut) -> bool:
    cust = _norm_place(state or "")
    if not cust:
        return False
    gstin_code = (company.gstin or "").strip()[:2]
    code = (company.state_code or gstin_code).strip()
    if code and cust == _norm_place(code):
        return True
    if gstin_code and cust == _norm_place(gstin_code):
        return True
    n_state = _norm_place(company.state)
    if n_state and cust == n_state:
        return True
    if len(n_state) >= 5 and len(cust) >= 5 and (n_state in cust or cust in n_state):
        return True
    abbrev = "".join(word[0] for word in (company.state or "").split() if word).lower()
    return bool(abbrev and cust == abbrev)


@dataclass(frozen=True)
class _LineIn:
    name: str
    unit_price: Decimal
    qty: int
    category: Category | None = None


@dataclass(frozen=True)
class _Alloc:
    net_incl: Decimal
    discount: Decimal
    charges: Decimal


def _allocate(
    lines: list[_LineIn],
    *,
    subtotal: Decimal,
    discount: Decimal,
    shipping: Decimal,
    platform_fee: Decimal,
    total: Decimal,
) -> list[_Alloc]:
    """Port of ``allocateOrderMoney`` in the invoice PDF."""
    grosses = [_r2(max(ZERO, line.unit_price) * max(1, line.qty)) for line in lines]
    items_gross = _r2(sum(grosses, ZERO))
    subtotal = _r2(subtotal) or items_gross
    discount = max(ZERO, _r2(discount))
    shipping = max(ZERO, _r2(shipping))
    platform_fee = max(ZERO, _r2(platform_fee))
    paid = _r2(total) or max(ZERO, subtotal + shipping + platform_fee - discount)

    base = items_gross if items_gross > 0 else subtotal
    discounts: list[Decimal] = []
    left = discount
    for i, gross in enumerate(grosses):
        if i == len(grosses) - 1:
            discounts.append(_r2(left))
        else:
            part = _r2(discount * (gross / base)) if base > 0 else ZERO
            discounts.append(part)
            left = _r2(left - part)

    last = len(grosses) - 1
    charges = [shipping + platform_fee if i == last else ZERO for i in range(len(grosses))]
    nets = [_r2(max(ZERO, g - d + c)) for g, d, c in zip(grosses, discounts, charges)]
    if nets:
        nets[last] = _r2(max(ZERO, paid - _r2(sum(nets[:last], ZERO))))
    return [_Alloc(n, d, c) for n, d, c in zip(nets, discounts, charges)]


@dataclass(frozen=True)
class _DocMeta:
    doc_type: str
    doc_date: str
    order_id: str
    channel: str
    store_name: str
    party_name: str
    place_of_supply: str
    intra_state: bool
    payment_mode: str
    narration: str
    original_date: str = ""


def _build_lines(
    meta: _DocMeta,
    lines: list[_LineIn],
    allocs: list[_Alloc],
    company: CompanyDetailsOut,
) -> list[SalesExportLine]:
    company_pct = max(ZERO, _dec(company.gst_percent))
    cgst_share = (
        min(Decimal(1), max(ZERO, _dec(company.cgst_percent) / company_pct))
        if company_pct > 0
        else Decimal("0.5")
    )

    out: list[SalesExportLine] = []
    for index, (line, alloc) in enumerate(zip(lines, allocs)):
        gst_pct = max(ZERO, effective_gst_percent(line.category, company_pct))
        divisor = 1 + gst_pct / 100
        net = alloc.net_incl
        taxable = _r2(net / divisor)
        gst = _r2(net - taxable)
        cgst = min(gst, max(ZERO, _r2(gst * cgst_share))) if meta.intra_state else ZERO
        sgst = _r2(gst - cgst) if meta.intra_state else ZERO
        igst = ZERO if meta.intra_state else gst
        inv_no = invoice_number(meta.order_id, index)
        is_credit = meta.doc_type == "credit_note"
        out.append(
            SalesExportLine(
                doc_type=meta.doc_type,
                doc_number=f"CN-{inv_no}" if is_credit else inv_no,
                doc_date=meta.doc_date,
                original_invoice_number=inv_no if is_credit else "",
                original_invoice_date=meta.original_date if is_credit else "",
                order_id=meta.order_id,
                channel=meta.channel,
                store_name=meta.store_name,
                party_name=meta.party_name,
                party_gstin="",
                place_of_supply=meta.place_of_supply,
                intra_state=meta.intra_state,
                item_name=line.name or "Eyewear",
                hsn_code=effective_hsn(line.category),
                uqc=UQC,
                quantity=max(1, line.qty),
                rate=float(_r2(max(ZERO, line.unit_price) / divisor)),
                discount=float(_r2(alloc.discount / divisor)),
                other_charges=float(_r2(alloc.charges / divisor)),
                taxable_value=float(taxable),
                gst_rate=float(gst_pct),
                cgst=float(cgst),
                sgst=float(sgst),
                igst=float(igst),
                cess=0,
                round_off=float(_r2(net - taxable - cgst - sgst - igst)),
                invoice_total=float(net),
                sales_ledger=f"Sales - GST {gst_pct.normalize():f}%",
                payment_mode=meta.payment_mode,
                narration=meta.narration,
            )
        )
    return out


def _web_lines(order: Order) -> list[_LineIn]:
    return [
        _LineIn(
            name=item.name_snapshot or (item.product.name if item.product else ""),
            unit_price=_dec(item.price_snapshot),
            qty=int(item.qty or 1),
            category=item.product.category if item.product else None,
        )
        for item in order.items or []
    ]


def _web_allocs(order: Order, lines: list[_LineIn]) -> list[_Alloc]:
    return _allocate(
        lines,
        subtotal=_dec(order.subtotal),
        discount=_dec(order.discount),
        shipping=_dec(order.shipping_fee),
        platform_fee=_dec(order.platform_fee),
        total=_dec(order.total),
    )


def _web_meta(order: Order, company: CompanyDetailsOut, *, doc_type: str, doc_dt: datetime | None) -> _DocMeta:
    pickup = (order.delivery or "").lower() == "pickup" or order.pickup_store_id is not None
    address = order.address
    if pickup:
        # Click & collect is supplied at our store, inside the seller's state.
        place, intra = company.state, True
    else:
        place = (address.state or "").strip() if address else ""
        intra = is_intra_state(place, company)
    customer = order.customer
    party = (customer.name if customer else None) or (customer.phone if customer else None) or "Customer"
    method = (order.payment_method or "").lower()
    pay = "Online" if method in {"razorpay", "online"} else "COD" if method in {"cod", "cash"} else method.upper()
    is_credit = doc_type == "credit_note"
    return _DocMeta(
        doc_type=doc_type,
        doc_date=_ddmmyyyy(doc_dt),
        original_date=_ddmmyyyy(order.created_at),
        order_id=order.order_number,
        channel="online",
        store_name=order.pickup_store.name if order.pickup_store else "",
        party_name=party,
        place_of_supply=place,
        intra_state=intra,
        payment_mode=pay,
        narration=(
            f"Refund for cancelled website order {order.order_number}"
            if is_credit
            else f"Website order {order.order_number}"
        ),
    )


def _store_lines(order: StoreOrder) -> list[_LineIn]:
    lines: list[_LineIn] = []
    for item in order.items or []:
        variant = item.variant
        product = variant.product if variant else None
        lines.append(
            _LineIn(
                name=(product.name if product else None) or (variant.sku if variant else "Item"),
                unit_price=_dec(item.price_snapshot),
                qty=int(item.qty or 1),
                category=product.category if product else None,
            )
        )
    return lines


def _store_doc(order: StoreOrder, company: CompanyDetailsOut) -> list[SalesExportLine]:
    lines = _store_lines(order)
    if not lines:
        return []
    total = _dec(order.total)
    allocs = _allocate(
        lines,
        subtotal=_dec(order.subtotal) or total,
        discount=ZERO,
        shipping=ZERO,
        platform_fee=ZERO,
        total=total,
    )
    store = order.store.name if order.store else ""
    method = (order.payment_method or "").lower()
    meta = _DocMeta(
        doc_type="invoice",
        doc_date=_ddmmyyyy(order.created_at),
        order_id=order.order_number,
        channel="store",
        store_name=store,
        party_name=order.customer_name or "Walk-in Customer",
        place_of_supply=company.state,
        intra_state=True,
        payment_mode=STORE_PAYMENT_LABEL.get(method, method.title()),
        narration=f"Store sale at {store} ({order.order_number})" if store else f"Store sale {order.order_number}",
    )
    return _build_lines(meta, lines, allocs, company)


def build_sales_export(db: Session, date_from: date, date_to: date) -> SalesExportResponse:
    """Invoices + credit notes in [date_from, date_to] (IST). Three queries, no N+1."""
    company = company_details(db)
    start, end = start_of_day(date_from), end_of_day(date_to)
    web_eager = (
        selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.category),
        selectinload(Order.address),
        selectinload(Order.customer),
        selectinload(Order.pickup_store),
    )

    # Unpaid orders that were cancelled never became a sale.
    web_orders = db.scalars(
        select(Order)
        .where(
            Order.created_at >= start,
            Order.created_at <= end,
            or_(Order.status != "cancelled", Order.payment_status == "paid"),
            or_(Order.payment_method != "razorpay", Order.payment_status == "paid"),
        )
        .options(*web_eager)
        .order_by(Order.created_at, Order.id)
    ).all()

    # Paid web orders cancelled in the range are refunded; updated_at is the cancel date.
    refunded = db.scalars(
        select(Order)
        .where(
            Order.status == "cancelled",
            Order.payment_status == "paid",
            Order.updated_at >= start,
            Order.updated_at <= end,
        )
        .options(*web_eager)
        .order_by(Order.updated_at, Order.id)
    ).all()

    # Click & collect web orders also have a StoreOrder twin — the web Order is the invoice.
    store_orders = db.scalars(
        select(StoreOrder)
        .where(
            StoreOrder.created_at >= start,
            StoreOrder.created_at <= end,
            ~exists().where(Order.order_number == StoreOrder.order_number),
        )
        .options(
            selectinload(StoreOrder.store),
            selectinload(StoreOrder.items)
            .selectinload(StoreOrderItem.variant)
            .selectinload(ProductVariant.product)
            .selectinload(Product.category),
        )
        .order_by(StoreOrder.created_at, StoreOrder.id)
    ).all()

    invoices: list[tuple[datetime, SalesExportLine]] = []
    for order in web_orders:
        lines = _web_lines(order)
        if not lines:
            continue
        meta = _web_meta(order, company, doc_type="invoice", doc_dt=order.created_at)
        for row in _build_lines(meta, lines, _web_allocs(order, lines), company):
            invoices.append((order.created_at, row))
    for order in store_orders:
        if (order.status or "").lower() in STORE_VOID_STATUSES:
            continue
        for row in _store_doc(order, company):
            invoices.append((order.created_at, row))
    invoices.sort(key=lambda pair: (pair[0] or datetime.min, pair[1].doc_number))

    credit_notes: list[SalesExportLine] = []
    for order in refunded:
        lines = _web_lines(order)
        if not lines:
            continue
        meta = _web_meta(order, company, doc_type="credit_note", doc_dt=order.updated_at)
        credit_notes.extend(_build_lines(meta, lines, _web_allocs(order, lines), company))

    return SalesExportResponse(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        seller_gstin=company.gstin,
        seller_state=company.state,
        invoices=[row for _, row in invoices],
        credit_notes=credit_notes,
    )
