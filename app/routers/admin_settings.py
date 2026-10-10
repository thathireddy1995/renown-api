"""Admin company settings — /admin/settings."""

from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from app.core.company_settings import from_settings_row, get_or_create_settings
from app.database import get_db
from app.deps import require_role
from app.dto.settings_dto import (
    AdminAppMaintenanceUpdate,
    AdminConfigurationUpdate,
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
    payload = from_settings_row(row).model_dump()
    payload["app_maintenance_enabled"] = bool(getattr(row, "app_maintenance_enabled", False))
    payload["app_maintenance_message"] = (
        getattr(row, "app_maintenance_message", None) or ""
    ).strip()
    payload["privacy_policy_url"] = (getattr(row, "privacy_policy_url", None) or "").strip()
    payload["terms_of_service_url"] = (getattr(row, "terms_of_service_url", None) or "").strip()
    payload["refund_policy_url"] = (getattr(row, "refund_policy_url", None) or "").strip()
    return AdminSettingsOut.model_validate(payload)


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


@router.patch("/app-maintenance", response_model=AdminSettingsOut)
def update_app_maintenance(
    payload: AdminAppMaintenanceUpdate,
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    row = get_or_create_settings(db)
    row.app_maintenance_enabled = payload.app_maintenance_enabled
    row.app_maintenance_message = payload.app_maintenance_message
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _out(row)


@router.patch("/configuration", response_model=AdminSettingsOut)
def update_configuration(
    payload: AdminConfigurationUpdate,
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    row = get_or_create_settings(db)
    row.app_maintenance_enabled = payload.app_maintenance_enabled
    row.app_maintenance_message = payload.app_maintenance_message
    row.privacy_policy_url = payload.privacy_policy_url
    row.terms_of_service_url = payload.terms_of_service_url
    row.refund_policy_url = payload.refund_policy_url
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
