from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TaxonomyOut(BaseModel):
    """Shape matching admin CrudTable Taxonomy rows."""

    id: str
    name: str
    slug: str
    products: int = 0
    status: str = "Active"
    updated: str = ""


class TaxonomyCreate(BaseModel):
    name: str = Field(max_length=120)
    slug: str | None = Field(default=None, max_length=140)
    status: str = "active"


class TaxonomyUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    slug: str | None = Field(default=None, max_length=140)
    status: str | None = None


class TaxonomyListResponse(BaseModel):
    items: list[TaxonomyOut]
    total: int
    limit: int
    offset: int


class AttributeOut(BaseModel):
    id: str
    name: str
    type: str
    values: list[str] = Field(default_factory=list)


class AttributeCreate(BaseModel):
    name: str = Field(max_length=120)
    type: str = "select"
    values: list[str] = Field(default_factory=list)


class AttributeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    type: str | None = None
    values: list[str] | None = None


class AttributeListResponse(BaseModel):
    items: list[AttributeOut]
    total: int
    limit: int
    offset: int


class AttributeValueCreate(BaseModel):
    value: str = Field(max_length=120)


class AttributeValueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attribute_id: int
    value: str


class CustomerCategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    image: str | None = None


class CustomerBrandOut(BaseModel):
    id: int
    name: str
    slug: str


class LensTypeOut(BaseModel):
    id: str
    name: str
    description: str = ""
    price: float = 0
    products: int = 0


class LensTypeCreate(BaseModel):
    name: str = Field(max_length=120)
    description: str | None = None
    price: Decimal = Decimal("0")


class LensTypeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    price: Decimal | None = None


class FrameTypeOut(BaseModel):
    id: str
    name: str
    description: str = ""
    products: int = 0


class FrameTypeCreate(BaseModel):
    name: str = Field(max_length=120)
    description: str | None = None


class FrameTypeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = None


class ColorOut(BaseModel):
    id: str
    name: str
    hex: str
    products: int = 0


class ColorCreate(BaseModel):
    name: str = Field(max_length=80)
    hex: str = Field(max_length=7)


class ColorUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    hex: str | None = Field(default=None, max_length=7)


class SizeOut(BaseModel):
    id: str
    name: str
    code: str
    measurement: str = ""
    products: int = 0


class SizeCreate(BaseModel):
    name: str = Field(max_length=80)
    code: str = Field(max_length=10)
    measurement: str | None = Field(default=None, max_length=40)


class SizeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    code: str | None = Field(default=None, max_length=10)
    measurement: str | None = Field(default=None, max_length=40)


class OpticalListResponse(BaseModel):
    items: list[LensTypeOut | FrameTypeOut | ColorOut | SizeOut]
    total: int
    limit: int
    offset: int


class LensTypeListResponse(BaseModel):
    items: list[LensTypeOut]
    total: int
    limit: int
    offset: int


class FrameTypeListResponse(BaseModel):
    items: list[FrameTypeOut]
    total: int
    limit: int
    offset: int


class ColorListResponse(BaseModel):
    items: list[ColorOut]
    total: int
    limit: int
    offset: int


class SizeListResponse(BaseModel):
    items: list[SizeOut]
    total: int
    limit: int
    offset: int
