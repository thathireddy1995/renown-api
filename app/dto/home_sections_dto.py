from pydantic import BaseModel, Field, field_validator

from app.dto.catalog_dto import ProductOut


class HomeSectionItemIn(BaseModel):
    id: int = Field(..., gt=0)
    label: str = Field(default="", max_length=60)
    sublabel: str = Field(default="", max_length=80)

    @field_validator("label", "sublabel", mode="before")
    @classmethod
    def _strip(cls, value: object) -> str:
        return str(value or "").strip()


class HomeSectionUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    subtitle: str = Field(default="", max_length=200)
    enabled: bool
    items: list[HomeSectionItemIn] = Field(default_factory=list, max_length=30)

    @field_validator("title", "subtitle", mode="before")
    @classmethod
    def _strip(cls, value: object) -> str:
        return str(value or "").strip()


class HomeSectionTileOut(BaseModel):
    id: int
    slug: str = ""
    name: str = ""
    image: str = ""
    label: str = ""
    sublabel: str = ""


class AdminHomeSectionOut(BaseModel):
    key: str
    title: str
    subtitle: str
    item_type: str
    enabled: bool
    items: list[HomeSectionTileOut]


class CustomerHomeSectionOut(BaseModel):
    key: str
    title: str
    subtitle: str
    item_type: str
    enabled: bool
    products: list[ProductOut] = Field(default_factory=list)
    tiles: list[HomeSectionTileOut] = Field(default_factory=list)


class CustomerHomeSectionsResponse(BaseModel):
    sections: list[CustomerHomeSectionOut]
