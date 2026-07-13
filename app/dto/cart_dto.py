from pydantic import BaseModel, Field


class CartItemOut(BaseModel):
    """Matches customer-renown store CartItem + row id for PATCH/DELETE."""

    id: int
    productId: str
    qty: int = 1
    savedForLater: bool = False
    variantId: int | None = None


class CartAddRequest(BaseModel):
    product_id: str = Field(description="Product slug or numeric id")
    variant_id: int | None = None
    qty: int = Field(default=1, ge=1)


class CartUpdateRequest(BaseModel):
    qty: int | None = Field(default=None, ge=1)
    saved_for_later: bool | None = None


class CartListResponse(BaseModel):
    items: list[CartItemOut]


class WishlistItemOut(BaseModel):
    id: int
    productId: str


class WishlistAddRequest(BaseModel):
    product_id: str


class WishlistListResponse(BaseModel):
    items: list[WishlistItemOut]


class CompareItemOut(BaseModel):
    id: int
    productId: str


class CompareAddRequest(BaseModel):
    product_id: str


class CompareListResponse(BaseModel):
    items: list[CompareItemOut]
