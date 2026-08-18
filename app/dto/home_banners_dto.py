"""DTOs shared by admin and customer homepage-banner endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.s3_images import public_url_for


def _validate_image_pair(image_url: str, image_key: str) -> None:
    if not image_key.startswith("homepage/banners/"):
        raise ValueError("Banner image must use the homepage/banners storage path.")
    if image_url != public_url_for(image_key):
        raise ValueError("Banner image URL does not match its S3 object key.")


class HomeBannerBase(BaseModel):
    eyebrow: str = Field(default="", max_length=80)
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(default="", max_length=300)
    brand_line: str = Field(default="", max_length=100)
    image_url: str = Field(min_length=1, max_length=1000)
    image_key: str = Field(min_length=1, max_length=500)
    image_alt: str = Field(default="", max_length=200)
    cta_label: str = Field(default="Shop Now", min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=120)
    sort_order: int = Field(default=0, ge=0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_image(self) -> "HomeBannerBase":
        _validate_image_pair(self.image_url, self.image_key)
        self.title = self.title.strip()
        self.category = self.category.strip() if self.category else None
        return self


class HomeBannerCreate(HomeBannerBase):
    pass


class HomeBannerUpdate(BaseModel):
    eyebrow: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    subtitle: str | None = Field(default=None, max_length=300)
    brand_line: str | None = Field(default=None, max_length=100)
    image_url: str | None = Field(default=None, min_length=1, max_length=1000)
    image_key: str | None = Field(default=None, min_length=1, max_length=500)
    image_alt: str | None = Field(default=None, max_length=200)
    cta_label: str | None = Field(default=None, min_length=1, max_length=60)
    category: str | None = Field(default=None, max_length=120)
    sort_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_image(self) -> "HomeBannerUpdate":
        if (self.image_url is None) != (self.image_key is None):
            raise ValueError("Image URL and image key must be updated together.")
        if self.image_url is not None and self.image_key is not None:
            _validate_image_pair(self.image_url, self.image_key)
        if self.title is not None:
            self.title = self.title.strip()
        if self.category is not None:
            self.category = self.category.strip() or None
        return self


class HomeBannerOut(HomeBannerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int | None = None
    updated_by: int | None = None
    created_at: datetime
    updated_at: datetime
