"""Pydantic DTOs for appointments, doctors, and prescriptions."""

from pydantic import BaseModel, Field


class DoctorOut(BaseModel):
    id: str
    name: str
    title: str
    years: int = 10


class DoctorListResponse(BaseModel):
    items: list[DoctorOut]


class BookAppointmentIn(BaseModel):
    store_id: int | None = None
    store: str | None = None
    doctor_id: int | str
    date: str
    time: str
    appointment_type: str = "eye_test"
    phone: str | None = None


class CustomerAppointmentOut(BaseModel):
    id: str
    store: str
    doctor: str
    date: str
    time: str


class CustomerAppointmentListResponse(BaseModel):
    items: list[CustomerAppointmentOut]
    total: int
    limit: int
    offset: int


class StaffAppointmentOut(BaseModel):
    id: str
    time: str
    customer: str
    phone: str
    type: str
    doctor: str
    status: str


class StaffAppointmentListResponse(BaseModel):
    items: list[StaffAppointmentOut]
    total: int
    limit: int
    offset: int


class StaffAppointmentCreate(BaseModel):
    customer: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=20)
    time: str = Field(min_length=1, max_length=40)
    date: str | None = None
    type: str = "Eye Test"
    doctor: str = Field(min_length=1, max_length=120)
    status: str = "Pending"
    store_id: int | None = None


class AppointmentStatusIn(BaseModel):
    status: str


class StaffPrescriptionOut(BaseModel):
    id: str
    customer: str
    date: str
    sphR: str
    cylR: str
    sphL: str
    cylL: str
    pd: str
    doctor: str
    phone: str = ""
    axisR: str = ""
    axisL: str = ""
    addR: str = ""
    addL: str = ""
    visionType: str = "single_vision"


class StaffPrescriptionListResponse(BaseModel):
    items: list[StaffPrescriptionOut]
    total: int
    limit: int
    offset: int


class StaffPrescriptionCreate(BaseModel):
    customer_id: int | None = None
    customer: str | None = None
    phone: str | None = None
    doctor_id: int | None = None
    doctor: str | None = None
    sphR: str = Field(default="0")
    cylR: str = Field(default="0")
    sphL: str = Field(default="0")
    cylL: str = Field(default="0")
    pd: str = Field(default="62")
    axisR: str = Field(default="", max_length=20)
    axisL: str = Field(default="", max_length=20)
    addR: str = Field(default="", max_length=20)
    addL: str = Field(default="", max_length=20)
    visionType: str = "single_vision"
    saveToProfile: bool = True
    date: str | None = None
