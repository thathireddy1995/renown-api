from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    phone: str | None
    role: str
    warehouse_id: int | None = None
    store_id: int | None = None
    warehouse_code: str | None = None
    warehouse_name: str | None = None
    warehouse_city: str | None = None
    store_code: str | None = None
    store_name: str | None = None
    store_city: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class AdminLoginRequest(BaseModel):
    mobile: str
    password: str


class StaffLoginRequest(BaseModel):
    phone: str
    password: str
    warehouse_id: int | None = None
    store_id: int | None = None
