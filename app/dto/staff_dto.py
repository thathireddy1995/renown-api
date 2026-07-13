"""Staff portal warehouse-ops request/response DTOs (UI camelCase shapes)."""

from pydantic import BaseModel, ConfigDict, Field


class StaffGrnOut(BaseModel):
    id: str
    po: str
    vendor: str
    items: int
    qty: int
    date: str
    status: str


class StaffGrnItemIn(BaseModel):
    variant_id: int
    qty_ordered: int = 0
    qty_received: int


class StaffGrnCreate(BaseModel):
    warehouse_id: int | None = None
    purchase_order_id: int | None = None
    po_number: str | None = None
    supplier_id: int | None = None
    status: str = "Done"
    items: list[StaffGrnItemIn] = Field(default_factory=list)


class StaffGrnListResponse(BaseModel):
    items: list[StaffGrnOut]
    total: int
    limit: int
    offset: int


class StaffPickListOut(BaseModel):
    id: str
    wave: str
    picker: str
    items: int
    progress: str
    status: str


class StaffPickItemPatch(BaseModel):
    item_id: int
    picked_qty: int


class StaffPickListPatch(BaseModel):
    picker: str | None = None
    status: str | None = None
    items: list[StaffPickItemPatch] = Field(default_factory=list)


class StaffPickListResponse(BaseModel):
    items: list[StaffPickListOut]
    total: int
    limit: int
    offset: int


class StaffPackOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    do: str = ""
    packer: str = ""
    boxes: int = 0
    weight: str = "—"
    status: str


class StaffPackCreate(BaseModel):
    dispatch_order_id: int | None = None
    do_number: str | None = None
    packer_name: str | None = None
    boxes: int = 0
    weight: float | None = None
    status: str = "Processing"


class StaffPackListResponse(BaseModel):
    items: list[StaffPackOut]
    total: int
    limit: int
    offset: int


class StaffDispatchOut(BaseModel):
    id: str
    destination: str
    type: str
    carrier: str
    awb: str
    items: int
    status: str


class StaffDispatchItemIn(BaseModel):
    variant_id: int
    qty: int


class StaffDispatchCreate(BaseModel):
    warehouse_id: int | None = None
    destination_type: str = "store_replen"
    destination_id: int | None = None
    destination_label: str | None = None
    carrier: str | None = None
    awb: str | None = None
    status: str = "Pending"
    items: list[StaffDispatchItemIn] = Field(default_factory=list)


class StaffDispatchListResponse(BaseModel):
    items: list[StaffDispatchOut]
    total: int
    limit: int
    offset: int


class StaffSupplierOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    contact: str = ""
    category: str = ""
    leadTime: str = ""
    openPO: int = 0
    status: str = "Active"


class StaffSupplierCreate(BaseModel):
    code: str | None = None
    name: str
    contact: str | None = None
    category: str | None = None
    lead_time_days: int = 0
    status: str = "Active"


class StaffSupplierUpdate(BaseModel):
    name: str | None = None
    contact: str | None = None
    category: str | None = None
    lead_time_days: int | None = None
    status: str | None = None


class StaffSupplierListResponse(BaseModel):
    items: list[StaffSupplierOut]
    total: int
    limit: int
    offset: int
