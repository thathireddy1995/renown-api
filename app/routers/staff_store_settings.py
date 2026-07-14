"""Staff store settings — /staff/store/settings."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import require_role, TokenPrincipal
from app.database import get_db
from app.schemas import Store

router = APIRouter(
    prefix="/staff/store/settings",
    tags=["staff-store-settings"],
    dependencies=[Depends(require_role("store_manager"))],
)


class StaffStoreSettingsOut(BaseModel):
    store_id: int
    name: str
    address: str = ""
    gstin: str = ""
    phone: str = ""
    sms_receipts: bool = True
    loyalty_discounts: bool = True
    manager_pin_refunds: bool = True
    click_collect: bool = False


class StaffStoreSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=200)
    gstin: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=40)
    sms_receipts: bool | None = None
    loyalty_discounts: bool | None = None
    manager_pin_refunds: bool | None = None
    click_collect: bool | None = None


# Preferences are not DB columns yet — keep last-known values in-process for the
# Lambda lifetime and return them with profile fields. Frontend also persists locally.
_PREFS: dict[int, dict[str, bool | str]] = {}


def _default_store(db: Session) -> Store | None:
    return db.scalar(
        select(Store).where(Store.status == "Open").order_by(Store.id.asc()).limit(1)
    ) or db.scalar(select(Store).order_by(Store.id.asc()).limit(1))


def _resolve_store(db: Session, principal: TokenPrincipal) -> Store | None:
    if principal.store_id is not None:
        return db.get(Store, principal.store_id)
    return _default_store(db)


def _prefs_for(store_id: int) -> dict[str, bool | str]:
    return _PREFS.setdefault(
        store_id,
        {
            "gstin": "",
            "sms_receipts": True,
            "loyalty_discounts": True,
            "manager_pin_refunds": True,
            "click_collect": False,
        },
    )


def _out(store: Store) -> StaffStoreSettingsOut:
    prefs = _prefs_for(store.id)
    return StaffStoreSettingsOut(
        store_id=store.id,
        name=store.name or "",
        address=store.address or "",
        gstin=str(prefs.get("gstin") or ""),
        phone=store.phone or "",
        sms_receipts=bool(prefs.get("sms_receipts", True)),
        loyalty_discounts=bool(prefs.get("loyalty_discounts", True)),
        manager_pin_refunds=bool(prefs.get("manager_pin_refunds", True)),
        click_collect=bool(prefs.get("click_collect", False)),
    )


@router.get("", response_model=StaffStoreSettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffStoreSettingsOut:
    store = _resolve_store(db, principal)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")
    return _out(store)


@router.put("", response_model=StaffStoreSettingsOut)
def save_settings(
    body: StaffStoreSettingsUpdate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("store_manager")),
) -> StaffStoreSettingsOut:
    store = _resolve_store(db, principal)
    if not store:
        raise HTTPException(status_code=400, detail="No store configured")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Store name is required")
        store.name = name
    if body.address is not None:
        store.address = body.address.strip() or None
    if body.phone is not None:
        store.phone = body.phone.strip() or None

    prefs = _prefs_for(store.id)
    if body.gstin is not None:
        prefs["gstin"] = body.gstin.strip()
    if body.sms_receipts is not None:
        prefs["sms_receipts"] = body.sms_receipts
    if body.loyalty_discounts is not None:
        prefs["loyalty_discounts"] = body.loyalty_discounts
    if body.manager_pin_refunds is not None:
        prefs["manager_pin_refunds"] = body.manager_pin_refunds
    if body.click_collect is not None:
        prefs["click_collect"] = body.click_collect

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(store)
    return _out(store)
