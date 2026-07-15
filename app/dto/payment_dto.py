from pydantic import BaseModel


class CreatePaymentOrderRequest(BaseModel):
    address_id: int | None = None
    delivery: str = "ship"  # ship | pickup
    coupon_code: str | None = None


class CreatePaymentOrderResponse(BaseModel):
    razorpay_order_id: str
    amount: int  # paise
    currency: str = "INR"
    razorpay_key: str
    amount_display: float  # rupees — for the frontend to show a summary


class VerifyPaymentRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str
    address_id: int | None = None
    delivery: str = "ship"
    coupon_code: str | None = None
    notes: str | None = None
