"""Admin CRUD/S3 upload and public mobile-banner feed."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import S3_PUBLIC_BUCKET
from app.core.s3_images import (
    delete_mobile_banner_object,
    presign_mobile_banner_puts,
)
from app.database import get_db
from app.deps import get_current_staff, require_role
from app.dto.catalog_dto import (
    ImagePresignItem,
    ImagePresignRequest,
    ImagePresignResponse,
)
from app.dto.mobile_banners_dto import (
    MobileBannerCreate,
    MobileBannerOut,
    MobileBannerUpdate,
)
from app.schemas import MobileBanner, User

admin_router = APIRouter(
    prefix="/admin/mobile-banners",
    tags=["admin-mobile-banners"],
    dependencies=[Depends(require_role("admin"))],
)
customer_router = APIRouter(
    prefix="/customer/mobile-banners",
    tags=["customer-mobile-banners"],
)


@admin_router.get("", response_model=list[MobileBannerOut])
def list_admin_mobile_banners(db: Session = Depends(get_db)) -> list[MobileBanner]:
    return list(
        db.scalars(
            select(MobileBanner).order_by(
                MobileBanner.sort_order.asc(),
                MobileBanner.id.asc(),
            )
        ).all()
    )


@customer_router.get("", response_model=list[MobileBannerOut])
def list_customer_mobile_banners(db: Session = Depends(get_db)) -> list[MobileBanner]:
    return list(
        db.scalars(
            select(MobileBanner)
            .where(MobileBanner.is_active.is_(True))
            .order_by(MobileBanner.sort_order.asc(), MobileBanner.id.asc())
        ).all()
    )


@admin_router.post(
    "/media/presign",
    response_model=ImagePresignResponse,
)
def presign_mobile_banner_media(
    payload: ImagePresignRequest,
) -> ImagePresignResponse:
    if len(payload.files) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select exactly one mobile banner file.",
        )
    uploads = presign_mobile_banner_puts(
        [(item.filename, item.content_type) for item in payload.files]
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@admin_router.post(
    "",
    response_model=MobileBannerOut,
    status_code=status.HTTP_201_CREATED,
)
def create_mobile_banner(
    payload: MobileBannerCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> MobileBanner:
    banner = MobileBanner(
        **payload.model_dump(),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(banner)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(banner)
    return banner


@admin_router.patch("/{banner_id}", response_model=MobileBannerOut)
def update_mobile_banner(
    banner_id: int,
    payload: MobileBannerUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> MobileBanner:
    banner = db.get(MobileBanner, banner_id)
    if banner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mobile banner not found.",
        )

    old_media_key = banner.media_key
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(banner, key, value)
    banner.updated_by = actor.id

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(banner)
    if banner.media_key != old_media_key:
        delete_mobile_banner_object(old_media_key)
    return banner


@admin_router.delete("/{banner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mobile_banner(
    banner_id: int,
    db: Session = Depends(get_db),
) -> None:
    banner = db.get(MobileBanner, banner_id)
    if banner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mobile banner not found.",
        )
    media_key = banner.media_key
    db.delete(banner)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    delete_mobile_banner_object(media_key)
