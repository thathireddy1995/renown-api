"""Staff warehouse settings — /staff/warehouse/settings."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import TokenPrincipal, require_role
from app.schemas import Warehouse

router = APIRouter(
    prefix="/staff/warehouse/settings",
    tags=["staff-warehouse-settings"],
    dependencies=[Depends(require_role("warehouse_manager"))],
)


class StaffWarehouseSettingsOut(BaseModel):
    warehouse_id: int
    name: str
    address: str = ""
    gstin: str = ""
    manager: str = ""
    auto_release_waves: bool = True
    dual_scan_dispatch: bool = True
    auto_po_low_stock: bool = False
    barcode_receiving: bool = True


class StaffWarehouseSettingsUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=200)
    gstin: str | None = Field(default=None, max_length=40)
    manager: str | None = Field(default=None, max_length=120)
    auto_release_waves: bool | None = None
    dual_scan_dispatch: bool | None = None
    auto_po_low_stock: bool | None = None
    barcode_receiving: bool | None = None


_PREFS: dict[int, dict[str, bool | str]] = {}


def _default_warehouse(db: Session) -> Warehouse | None:
    return db.scalar(select(Warehouse).order_by(Warehouse.id.asc()).limit(1))


def _resolve_warehouse(db: Session, principal: TokenPrincipal) -> Warehouse | None:
    if principal.warehouse_id is not None:
        return db.get(Warehouse, principal.warehouse_id)
    return _default_warehouse(db)


def _prefs_for(warehouse_id: int) -> dict[str, bool | str]:
    return _PREFS.setdefault(
        warehouse_id,
        {
            "address": "",
            "gstin": "",
            "auto_release_waves": True,
            "dual_scan_dispatch": True,
            "auto_po_low_stock": False,
            "barcode_receiving": True,
        },
    )


def _out(wh: Warehouse) -> StaffWarehouseSettingsOut:
    prefs = _prefs_for(wh.id)
    return StaffWarehouseSettingsOut(
        warehouse_id=wh.id,
        name=wh.name or "",
        address=str(prefs.get("address") or ""),
        gstin=str(prefs.get("gstin") or ""),
        manager=wh.manager or "",
        auto_release_waves=bool(prefs.get("auto_release_waves", True)),
        dual_scan_dispatch=bool(prefs.get("dual_scan_dispatch", True)),
        auto_po_low_stock=bool(prefs.get("auto_po_low_stock", False)),
        barcode_receiving=bool(prefs.get("barcode_receiving", True)),
    )


@router.get("", response_model=StaffWarehouseSettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
) -> StaffWarehouseSettingsOut:
    wh = _resolve_warehouse(db, principal)
    if not wh:
        raise HTTPException(status_code=400, detail="No warehouse configured")
    return _out(wh)


@router.put("", response_model=StaffWarehouseSettingsOut)
def save_settings(
    body: StaffWarehouseSettingsUpdate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("warehouse_manager")),
) -> StaffWarehouseSettingsOut:
    wh = _resolve_warehouse(db, principal)
    if not wh:
        raise HTTPException(status_code=400, detail="No warehouse configured")

    data = body.model_dump(exclude_unset=True)
    prefs = _prefs_for(wh.id)

    if "name" in data and data["name"] is not None:
        wh.name = str(data["name"]).strip() or wh.name
    if "manager" in data and data["manager"] is not None:
        wh.manager = str(data["manager"]).strip() or None

    for key in (
        "address",
        "gstin",
        "auto_release_waves",
        "dual_scan_dispatch",
        "auto_po_low_stock",
        "barcode_receiving",
    ):
        if key in data and data[key] is not None:
            prefs[key] = data[key]

    db.commit()
    db.refresh(wh)
    return _out(wh)
