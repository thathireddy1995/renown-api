"""Admin CRUD/S3 upload and public homepage-banner feed."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.s3_images import (
    delete_banner_object,
    presign_banner_puts,
)
from app.database import get_db
from app.deps import get_current_staff, require_role
from app.dto.catalog_dto import (
    ImagePresignItem,
    ImagePresignRequest,
    ImagePresignResponse,
)
from app.dto.home_banners_dto import (
    HomeBannerCreate,
    HomeBannerOut,
    HomeBannerUpdate,
)
from app.schemas import HomeBanner, User
from app.core.config import S3_PUBLIC_BUCKET

admin_router = APIRouter(
    prefix="/admin/home-banners",
    tags=["admin-home-banners"],
    dependencies=[Depends(require_role("admin"))],
)
customer_router = APIRouter(
    prefix="/customer/home-banners",
    tags=["customer-home-banners"],
)


@admin_router.get("", response_model=list[HomeBannerOut])
def list_admin_home_banners(db: Session = Depends(get_db)) -> list[HomeBanner]:
    return list(
        db.scalars(
            select(HomeBanner).order_by(
                HomeBanner.sort_order.asc(),
                HomeBanner.id.asc(),
            )
        ).all()
    )


@customer_router.get("", response_model=list[HomeBannerOut])
def list_customer_home_banners(db: Session = Depends(get_db)) -> list[HomeBanner]:
    return list(
        db.scalars(
            select(HomeBanner)
            .where(HomeBanner.is_active.is_(True))
            .order_by(HomeBanner.sort_order.asc(), HomeBanner.id.asc())
        ).all()
    )


@admin_router.post(
    "/images/presign",
    response_model=ImagePresignResponse,
)
def presign_home_banner_image(
    payload: ImagePresignRequest,
) -> ImagePresignResponse:
    if len(payload.files) != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Select exactly one banner image.",
        )
    uploads = presign_banner_puts(
        [(item.filename, item.content_type) for item in payload.files]
    )
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@admin_router.post(
    "",
    response_model=HomeBannerOut,
    status_code=status.HTTP_201_CREATED,
)
def create_home_banner(
    payload: HomeBannerCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> HomeBanner:
    banner = HomeBanner(
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


@admin_router.patch("/{banner_id}", response_model=HomeBannerOut)
def update_home_banner(
    banner_id: int,
    payload: HomeBannerUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> HomeBanner:
    banner = db.get(HomeBanner, banner_id)
    if banner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Homepage banner not found.",
        )

    old_image_key = banner.image_key
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
    if banner.image_key != old_image_key:
        delete_banner_object(old_image_key)
    return banner


@admin_router.delete("/{banner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_home_banner(
    banner_id: int,
    db: Session = Depends(get_db),
) -> None:
    banner = db.get(HomeBanner, banner_id)
    if banner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Homepage banner not found.",
        )
    image_key = banner.image_key
    db.delete(banner)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    delete_banner_object(image_key)
