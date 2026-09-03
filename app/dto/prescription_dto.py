"""Customer saved prescription (power / Rx) DTOs."""

from pydantic import BaseModel, Field


class EyeRxIn(BaseModel):
    sph: str = ""
    cyl: str = ""
    axis: str = ""
    pd: str = ""
    add: str = ""


class CustomerPrescriptionOut(BaseModel):
    id: int
    customer_id: int
    power_mode: str = "powered"
    vision_type: str = "single_vision"
    lens_type: str | None = None
    right: EyeRxIn
    left: EyeRxIn
    power_summary: str = ""
    updated_at: str | None = None


class CustomerPrescriptionUpsert(BaseModel):
    power_mode: str = Field(default="powered")
    vision_type: str = Field(default="single_vision")
    lens_type: str | None = None
    right: EyeRxIn = Field(default_factory=EyeRxIn)
    left: EyeRxIn = Field(default_factory=EyeRxIn)
