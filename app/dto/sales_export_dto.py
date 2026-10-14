"""Admin Cashbook sales export (Tally sales + GSTR-1 data)."""

from typing import Literal

from pydantic import BaseModel, Field


class SalesExportLine(BaseModel):
    """One invoice / credit-note line. Amounts are numbers in INR, dates DD-MM-YYYY."""

    doc_type: Literal["invoice", "credit_note"]
    doc_number: str
    doc_date: str
    original_invoice_number: str = ""
    original_invoice_date: str = ""
    order_id: str
    channel: Literal["online", "store"]
    store_name: str = ""
    party_name: str
    party_gstin: str = ""
    place_of_supply: str = ""
    intra_state: bool
    item_name: str
    hsn_code: str
    uqc: str
    quantity: int
    rate: float
    discount: float
    other_charges: float
    taxable_value: float
    gst_rate: float
    cgst: float
    sgst: float
    igst: float
    cess: float = 0
    round_off: float = 0
    invoice_total: float
    sales_ledger: str
    payment_mode: str
    narration: str


class SalesExportResponse(BaseModel):
    date_from: str
    date_to: str
    seller_gstin: str
    seller_state: str
    invoices: list[SalesExportLine] = Field(default_factory=list)
    credit_notes: list[SalesExportLine] = Field(default_factory=list)
