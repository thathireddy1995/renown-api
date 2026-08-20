"""Homepage widget payload for the customer storefront."""

from pydantic import BaseModel, Field


class HomeBannerCard(BaseModel):
    id: int
    eyebrow: str = ""
    title: str
    subtitle: str = ""
    brand_line: str = ""
    image_url: str
    image_alt: str = ""
    cta_label: str = "Shop Now"
    category: str | None = None
    sort_order: int = 0
    is_active: bool = True


class HomeCategoryTile(BaseModel):
    id: int
    slug: str
    name: str
    image: str = ""
    count: int = 0


class HomeProductCard(BaseModel):
    id: str
    name: str
    price: float
    image: str = ""
    stock: int = 0
    rating: float = 0
    colorSwatches: list[str] = Field(default_factory=list, max_length=3)


class CustomerHomeResponse(BaseModel):
    banners: list[HomeBannerCard] = Field(default_factory=list)
    categories: list[HomeCategoryTile] = Field(default_factory=list)
    products: list[HomeProductCard] = Field(default_factory=list)
    featured: list[str] = Field(default_factory=list)
    bestsellers: list[str] = Field(default_factory=list)
    newArrivals: list[str] = Field(default_factory=list)
