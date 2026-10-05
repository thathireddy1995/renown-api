"""Customer push tokens — /customer/push-tokens (JWT required)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_customer
from app.dto.push_dto import PushTokenRegisterRequest, PushTokenRemoveRequest
from app.schemas import Customer, CustomerPushToken

router = APIRouter(prefix="/customer/push-tokens", tags=["customer-push"])


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
def register_push_token(
    payload: PushTokenRegisterRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    row = db.scalar(select(CustomerPushToken).where(CustomerPushToken.token == payload.token))
    if row:
        row.customer_id = customer.id
        row.platform = payload.platform
    else:
        db.add(
            CustomerPushToken(
                customer_id=customer.id, token=payload.token, platform=payload.platform
            )
        )
    db.commit()


@router.post("/remove", status_code=status.HTTP_204_NO_CONTENT)
def remove_push_token(
    payload: PushTokenRemoveRequest,
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> None:
    db.execute(
        delete(CustomerPushToken).where(
            CustomerPushToken.token == payload.token,
            CustomerPushToken.customer_id == customer.id,
        )
    )
    db.commit()
