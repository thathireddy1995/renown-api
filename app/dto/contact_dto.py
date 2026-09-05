from pydantic import BaseModel, Field, field_validator


class ContactRequestIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    phone: str = Field(..., min_length=10, max_length=16)
    message: str = Field(..., min_length=1, max_length=2000)

    @field_validator("name", "message")
    @classmethod
    def strip_required(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("This field is required")
        return text

    @field_validator("phone")
    @classmethod
    def ten_digit_phone(cls, value: str) -> str:
        digits = "".join(ch for ch in (value or "") if ch.isdigit())
        if len(digits) != 10:
            raise ValueError("Enter a valid 10-digit mobile number")
        return digits


class ContactRequestOut(BaseModel):
    ok: bool = True
    message: str = "Thanks — we'll get back to you shortly."
