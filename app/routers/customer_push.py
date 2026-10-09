"""Customer push tokens and inbox — /customer/push-tokens, /customer/notifications (JWT)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_customer
from app.dto.push_dto import (
    CustomerNotificationListResponse,
    CustomerNotificationOut,
    PushTokenRegisterRequest,
    PushTokenRemoveRequest,
)
from app.schemas import Customer, CustomerPushToken, PushNotificationLog

router = APIRouter(prefix="/customer/push-tokens", tags=["customer-push"])
inbox_router = APIRouter(prefix="/customer/notifications", tags=["customer-push"])


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


@inbox_router.get("", response_model=CustomerNotificationListResponse)
def list_customer_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    customer: Customer = Depends(get_current_customer),
) -> CustomerNotificationListResponse:
    rows = db.scalars(
        select(PushNotificationLog)
        .where(
            or_(
                PushNotificationLog.audience == "all",
                PushNotificationLog.customer_id == customer.id,
            ),
            PushNotificationLog.sent > 0,
        )
        .order_by(PushNotificationLog.created_at.desc())
        .limit(limit)
    ).all()
    return CustomerNotificationListResponse(
        items=[CustomerNotificationOut.model_validate(r) for r in rows]
    )
