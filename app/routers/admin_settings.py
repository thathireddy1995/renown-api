"""Admin company settings — /admin/settings."""

from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.orm import Session

from app.core.company_settings import (
    contact_lens_images,
    from_settings_row,
    get_or_create_settings,
)
from app.core.config import S3_PUBLIC_BUCKET
from app.core.s3_images import is_app_tile_url, presign_app_tile_puts
from app.database import get_db
from app.deps import require_role
from app.dto.catalog_dto import (
    ImagePresignItem,
    ImagePresignRequest,
    ImagePresignResponse,
)
from app.dto.settings_dto import (
    AdminAppMaintenanceUpdate,
    AdminConfigurationUpdate,
    AdminContactLensImagesUpdate,
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
    payload["app_contact_lens_images"] = contact_lens_images(row)
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


@router.post("/app-tiles/presign", response_model=ImagePresignResponse)
def presign_app_tile(payload: ImagePresignRequest) -> ImagePresignResponse:
    if len(payload.files) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select exactly one image.",
        )
    uploads = presign_app_tile_puts(
        [(item.filename, item.content_type) for item in payload.files]
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@router.patch("/contact-lens-images", response_model=AdminSettingsOut)
def update_contact_lens_images(
    payload: AdminContactLensImagesUpdate,
    db: Session = Depends(get_db),
) -> AdminSettingsOut:
    images = {slot: url for slot, url in payload.model_dump().items() if url}
    bad = [slot for slot, url in images.items() if not is_app_tile_url(url)]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Upload the {', '.join(bad)} image again.",
        )
    row = get_or_create_settings(db)
    row.app_contact_lens_images = images
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
