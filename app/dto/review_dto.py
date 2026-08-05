from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewImageIn(BaseModel):
    url: str


class ReviewCreateRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    title: str | None = Field(None, max_length=160)
    body: str = Field(..., min_length=10, max_length=4000)
    images: list[ReviewImageIn] = Field(default_factory=list, max_length=3)


class ReviewImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    sort_order: int


class ReviewOut(BaseModel):
    id: int
    rating: int
    title: str | None
    body: str
    author_name: str
    verified_purchase: bool = True
    images: list[ReviewImageOut]
    created_at: datetime


class ReviewListResponse(BaseModel):
    items: list[ReviewOut]
    total: int
    average_rating: float
    rating_breakdown: dict[str, int]
    limit: int
    offset: int


class ReviewEligibilityResponse(BaseModel):
    can_review: bool
    reason: str | None = None
    already_reviewed: bool = False
    has_delivered_purchase: bool = False
