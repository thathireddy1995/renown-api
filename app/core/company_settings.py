"""Load the singleton company settings row without N+1 lookups."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.dto.settings_dto import CONTACT_LENS_SLOTS, CompanyDetailsOut
from app.schemas import SystemSettings

_FALLBACK = CompanyDetailsOut(
    brand_name="Renown Eye Wear",
    legal_name="KOMMA CHANDRA SEKHAR",
    phone="+91 96425 12952",
    email="support@renowneyewear.com",
    website="www.renowneyewear.com",
    address_line1="4-88, Ramdas colony",
    address_line2="Nearby Overhead Tank, Vedantha Puram",
    city="Tirupati",
    state="Andhra Pradesh",
    postal_code="517508",
    country="India",
    gstin="37FQKPK5154A1ZV",
    state_code="37",
    gst_percent=5,
    sgst_percent=2.5,
    cgst_percent=2.5,
    igst_percent=5,
)


def from_settings_row(row: SystemSettings) -> CompanyDetailsOut:
    return CompanyDetailsOut(
        brand_name=row.brand_name,
        legal_name=row.legal_name,
        phone=row.phone,
        email=row.email,
        website=row.website,
        address_line1=row.address_line1,
        address_line2=row.address_line2,
        city=row.city,
        state=row.state,
        postal_code=row.postal_code,
        country=row.country,
        gstin=row.gstin,
        state_code=row.state_code,
        gst_percent=float(row.gst_percent),
        sgst_percent=float(row.sgst_percent),
        cgst_percent=float(row.cgst_percent),
        igst_percent=float(row.igst_percent),
    )


def _normalize_website(url: str) -> str:
    raw = (url or "").strip() or "renowneyewear.com"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return f"https://{raw.lstrip('/')}"


def contact_lens_images(row: SystemSettings) -> dict[str, str]:
    raw = getattr(row, "app_contact_lens_images", None) or {}
    return {
        slot: raw[slot]
        for slot in CONTACT_LENS_SLOTS
        if isinstance(raw.get(slot), str) and raw[slot]
    }


@dataclass(frozen=True)
class CheckoutCharges:
    shipping_fee: Decimal = Decimal("0")
    free_shipping_above: Decimal = Decimal("0")
    platform_fee: Decimal = Decimal("0")

    def shipping_for(self, subtotal: Decimal, delivery: str) -> Decimal:
        if delivery == "pickup" or subtotal <= 0 or self.shipping_fee <= 0:
            return Decimal("0")
        if self.free_shipping_above > 0 and subtotal >= self.free_shipping_above:
            return Decimal("0")
        return self.shipping_fee

    def platform_for(self, subtotal: Decimal) -> Decimal:
        if subtotal <= 0 or self.platform_fee <= 0:
            return Decimal("0")
        return self.platform_fee

    def as_public(self) -> dict[str, float]:
        return {
            "shipping_fee": float(self.shipping_fee),
            "free_shipping_above": float(self.free_shipping_above),
            "platform_fee": float(self.platform_fee),
        }


def _money(value: object) -> Decimal:
    try:
        amount = Decimal(str(value if value is not None else 0))
        return amount if amount > 0 else Decimal("0")
    except (ArithmeticError, ValueError):
        return Decimal("0")


def charges_from_row(row: SystemSettings | None) -> CheckoutCharges:
    if row is None:
        return CheckoutCharges()
    return CheckoutCharges(
        shipping_fee=_money(getattr(row, "shipping_fee", 0)),
        free_shipping_above=_money(getattr(row, "free_shipping_above", 0)),
        platform_fee=_money(getattr(row, "platform_fee", 0)),
    )


def checkout_charges(db: Session) -> CheckoutCharges:
    """Admin-configured shipping / platform fees. One PK lookup, never writes."""
    return charges_from_row(db.get(SystemSettings, 1))


def app_status_public(db: Session) -> dict[str, object]:
    try:
        row = get_or_create_settings(db)
    except ProgrammingError:
        db.rollback()
        return {
            "maintenance_enabled": False,
            "message": "",
            "website_url": "https://renowneyewear.com",
            "support_phone": _FALLBACK.phone,
            "contact_lens_images": {},
            "charges": CheckoutCharges().as_public(),
        }
    return {
        "maintenance_enabled": bool(getattr(row, "app_maintenance_enabled", False)),
        "message": (getattr(row, "app_maintenance_message", None) or "").strip(),
        "website_url": _normalize_website(row.website),
        "support_phone": row.phone or _FALLBACK.phone,
        "contact_lens_images": contact_lens_images(row),
        "charges": charges_from_row(row).as_public(),
    }


def get_or_create_settings(db: Session) -> SystemSettings:
    row = db.get(SystemSettings, 1)
    if row is not None:
        return row
    row = SystemSettings(id=1)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.get(SystemSettings, 1)
        if row is None:
            raise
        return row
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def company_details(db: Session) -> CompanyDetailsOut:
    """Read-only snapshot for invoices. One PK lookup, never writes."""
    try:
        row = db.get(SystemSettings, 1)
    except ProgrammingError:
        db.rollback()
        return _FALLBACK
    if row is None:
        return _FALLBACK
    return from_settings_row(row)


def seller_public(db: Session) -> dict[str, str]:
    details = company_details(db)
    return {
        "trade_name": details.brand_name,
        "gstin": details.gstin,
        "state": details.state,
        "city": details.city,
        "website": details.website,
    }
