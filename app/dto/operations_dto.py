"""DTOs for import/export, bulk upload, audits, low stock."""

from pydantic import BaseModel, Field


class ImportJobOut(BaseModel):
    id: str
    file: str
    rows: int
    status: str
    by: str
    date: str


class ImportJobListResponse(BaseModel):
    items: list[ImportJobOut]
    total: int
    limit: int
    offset: int


class BulkUploadRow(BaseModel):
    name: str = ""
    brand: str = ""
    sku: str = ""
    category: str = ""
    price: float = 0
    stock: int = 0
    color: str = ""
    size: str = ""


class BulkUploadRequest(BaseModel):
    file_name: str = "upload.csv"
    rows: list[BulkUploadRow] = Field(default_factory=list)
    created_by: str | None = None


class BulkUploadPreviewRow(BaseModel):
    row: int
    name: str
    brand: str
    sku: str
    price: float
    stock: int
    valid: bool
    error: str | None = None


class BulkUploadValidateResponse(BaseModel):
    total: int
    valid: int
    errors: int
    preview: list[BulkUploadPreviewRow]


class BulkUploadResponse(BaseModel):
    job_id: str
    imported: int
    errors: int
    status: str


class AuditOut(BaseModel):
    id: str
    zone: str
    counted: int
    expected: int
    variance: int
    auditor: str
    date: str
    status: str


class AuditListResponse(BaseModel):
    items: list[AuditOut]
    total: int
    limit: int
    offset: int


class AuditCreate(BaseModel):
    warehouse_id: int | None = None
    zone: str = "A · Frames"
    auditor_name: str | None = None


class AuditItemCountIn(BaseModel):
    counted_qty: int


class LowStockOut(BaseModel):
    id: str
    sku: str
    product: str
    onHand: int
    reorder: int
    suggested: int
    supplier: str
    status: str


class LowStockListResponse(BaseModel):
    items: list[LowStockOut]
    total: int
    limit: int
    offset: int
