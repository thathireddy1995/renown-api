from pydantic import BaseModel, ConfigDict


class OtpRequest(BaseModel):
    phone: str


class OtpVerifyRequest(BaseModel):
    phone: str
    code: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class CustomerLoginRequest(BaseModel):
    phone: str
    password: str


class RegisterRequestOtp(BaseModel):
    name: str
    phone: str


class RegisterCompleteRequest(BaseModel):
    name: str
    phone: str
    code: str
    password: str


class ForgotPasswordRequestOtp(BaseModel):
    phone: str


class ForgotPasswordCompleteRequest(BaseModel):
    phone: str
    code: str
    password: str


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    phone: str | None
    email: str | None


class CustomerTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer: CustomerOut


class OtpRequestResponse(BaseModel):
    message: str
    expires_in_seconds: int
