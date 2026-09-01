from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


def _strip(value: str | None) -> str:
    return (value or "").strip()


class CompanyDetailsOut(BaseModel):
    """Public company profile used on tax invoices."""

    brand_name: str
    legal_name: str
    phone: str
    email: str
    website: str
    address_line1: str
    address_line2: str
    city: str
    state: str
    postal_code: str
    country: str
    gstin: str
    state_code: str
    gst_percent: float
    sgst_percent: float
    cgst_percent: float
    igst_percent: float


class AdminSettingsOut(CompanyDetailsOut):
    pass


class AdminGeneralSettingsUpdate(BaseModel):
    brand_name: str = Field(min_length=1, max_length=120)
    legal_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(max_length=40)
    email: str = Field(max_length=160)
    website: str = Field(max_length=160)
    address_line1: str = Field(min_length=1, max_length=160)
    address_line2: str = Field(default="", max_length=160)
    city: str = Field(max_length=80)
    state: str = Field(min_length=1, max_length=80)
    postal_code: str = Field(max_length=12)
    country: str = Field(max_length=60)

    @field_validator(
        "brand_name",
        "legal_name",
        "phone",
        "email",
        "website",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "postal_code",
        "country",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str:
        return _strip(value)


class AdminGstSettingsUpdate(BaseModel):
    gstin: str = Field(min_length=15, max_length=15)
    state_code: str = Field(default="", max_length=2)
    gst_percent: Decimal
    sgst_percent: Decimal
    cgst_percent: Decimal
    igst_percent: Decimal

    @field_validator("gstin", "state_code", mode="before")
    @classmethod
    def strip_upper(cls, value: str | None) -> str:
        return _strip(value).upper()

    @field_validator("gstin")
    @classmethod
    def gstin_shape(cls, value: str) -> str:
        if not value.isalnum() or len(value) != 15:
            raise ValueError("GSTIN must be 15 letters or digits.")
        return value

    @field_validator("gst_percent", "sgst_percent", "cgst_percent", "igst_percent")
    @classmethod
    def rate_bounds(cls, value: Decimal) -> Decimal:
        if value < 0 or value > 100:
            raise ValueError("Tax percent must be between 0 and 100.")
        return value

    @model_validator(mode="after")
    def align_state_and_splits(self) -> "AdminGstSettingsUpdate":
        # GSTIN prefix is the legal state code; keep invoices in sync with it.
        self.state_code = self.gstin[:2]
        split = self.cgst_percent + self.sgst_percent
        if (split - self.gst_percent).copy_abs() > Decimal("0.05"):
            raise ValueError("CGST % + SGST % must equal GST %.")
        if (self.igst_percent - self.gst_percent).copy_abs() > Decimal("0.05"):
            raise ValueError("IGST % must equal GST %.")
        return self
