"""Admin Cashbook DTOs."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

IN_CATEGORIES = ("Eye test fee", "Advance payment", "Owner deposit", "Opening balance", "Other income")
OUT_CATEGORIES = (
    "Bank deposit",
    "Staff salary",
    "Rent",
    "Electricity",
    "Supplier payment",
    "Tea / snacks",
    "Courier",
    "Repairs",
    "Other expense",
)


class CashbookStoreOut(BaseModel):
    id: int
    name: str


class CashbookEntryOut(BaseModel):
    id: str
    source: Literal["manual", "store_sale", "online_sale", "refund"]
    store_id: int | None = None
    store: str
    date: str
    time: str
    type: Literal["in", "out"]
    category: str
    mode: str
    amount: float
    note: str = ""
    entered_by: str = ""


class CashbookResponse(BaseModel):
    date_from: str
    date_to: str
    opening_balance: float
    stores: list[CashbookStoreOut]
    entries: list[CashbookEntryOut]


class CashbookEntryCreate(BaseModel):
    store_id: int | None = None
    entry_date: date
    entry_type: Literal["in", "out"]
    category: str = Field(min_length=1, max_length=60)
    mode: Literal["Cash", "UPI", "Card", "Bank"] = "Cash"
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("category", "note", mode="before")
    @classmethod
    def strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value
