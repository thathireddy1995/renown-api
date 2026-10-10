"""Load the singleton company settings row without N+1 lookups."""

from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.dto.settings_dto import CompanyDetailsOut
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
        }
    return {
        "maintenance_enabled": bool(getattr(row, "app_maintenance_enabled", False)),
        "message": (getattr(row, "app_maintenance_message", None) or "").strip(),
        "website_url": _normalize_website(row.website),
        "support_phone": row.phone or _FALLBACK.phone,
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
