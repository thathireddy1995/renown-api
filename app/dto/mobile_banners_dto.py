"""DTOs shared by admin and customer mobile-banner endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.s3_images import infer_mobile_media_type, public_url_for

MOBILE_BANNER_PREFIX = "homepage/mobile-banners/"


def _validate_media_pair(media_url: str, media_key: str) -> None:
    if not media_key.startswith(MOBILE_BANNER_PREFIX):
        raise ValueError("Mobile banner media must use the homepage/mobile-banners storage path.")
    if media_url != public_url_for(media_key):
        raise ValueError("Mobile banner media URL does not match its S3 object key.")


class MobileBannerBase(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=300)
    media_url: str = Field(min_length=1, max_length=1000)
    media_key: str = Field(min_length=1, max_length=500)
    media_type: str = Field(default="image", max_length=20)
    media_alt: str = Field(default="", max_length=200)
    cta_label: str = Field(default="Shop Now", min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=120)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_media(self) -> "MobileBannerBase":
        _validate_media_pair(self.media_url, self.media_key)
        self.title = self.title.strip()
        self.subtitle = self.subtitle.strip()
        self.media_alt = self.media_alt.strip()
        self.cta_label = self.cta_label.strip() or "Shop Now"
        self.category = self.category.strip() if self.category else None
        self.media_type = infer_mobile_media_type(self.media_key, self.media_type)
        return self


class MobileBannerCreate(MobileBannerBase):
    pass


class MobileBannerUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    subtitle: str | None = Field(default=None, max_length=300)
    media_url: str | None = Field(default=None, min_length=1, max_length=1000)
    media_key: str | None = Field(default=None, min_length=1, max_length=500)
    media_type: str | None = Field(default=None, max_length=20)
    media_alt: str | None = Field(default=None, max_length=200)
    cta_label: str | None = Field(default=None, min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=120)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_media(self) -> "MobileBannerUpdate":
        if (self.media_url is None) != (self.media_key is None):
            raise ValueError("Media URL and media key must be updated together.")
        if self.media_url is not None and self.media_key is not None:
            _validate_media_pair(self.media_url, self.media_key)
            self.media_type = infer_mobile_media_type(
                self.media_key,
                self.media_type or "image",
            )
        if self.title is not None:
            self.title = self.title.strip()
        if self.subtitle is not None:
            self.subtitle = self.subtitle.strip()
        if self.media_alt is not None:
            self.media_alt = self.media_alt.strip()
        if self.cta_label is not None:
            self.cta_label = self.cta_label.strip() or "Shop Now"
        if self.category is not None:
            self.category = self.category.strip() or None
        return self


class MobileBannerOut(MobileBannerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime
    updated_at: datetime
