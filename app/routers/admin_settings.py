"""Admin company settings — /admin/settings."""

from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.core.company_settings import from_settings_row, get_or_create_settings
from app.database import get_db
from app.deps import require_role
from app.dto.settings_dto import (
    AdminGeneralSettingsUpdate,
    AdminGstSettingsUpdate,
    AdminSettingsOut,
)

router = APIRouter(
    prefix="/admin/settings",
    tags=["admin-settings"],
    dependencies=[Depends(require_role("admin"))],
)


def _out(row) -> AdminSettingsOut:
    return AdminSettingsOut.model_validate(from_settings_row(row))


@router.get("", response_model=AdminSettingsOut)
def get_settings(db: Session = Depends(get_db)) -> AdminSettingsOut:
    return _out(get_or_create_settings(db))


@router.patch("/general", response_model=AdminSettingsOut)
def update_general(
    payload: AdminGeneralSettingsUpdate,
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    row = get_or_create_settings(db)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _out(row)


@router.patch("/gst", response_model=AdminSettingsOut)
def update_gst(
    payload: AdminGstSettingsUpdate,
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    row = get_or_create_settings(db)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _out(row)
