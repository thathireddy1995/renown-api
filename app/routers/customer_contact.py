"""Public storefront contact form — /customer/contact.

No JWT: anyone can write in. The message is enqueued on the same Optimus SQS
queue as order confirmations and posted to Renown Notifications on Telegram.
"""

from fastapi import APIRouter, HTTPException, status

from app.dto.contact_dto import ContactRequestIn, ContactRequestOut
from app.routers.telegram_notify import notify_contact_request

router = APIRouter(prefix="/customer", tags=["customer-contact"])


@router.post("/contact", response_model=ContactRequestOut)
def submit_contact_request(payload: ContactRequestIn) -> ContactRequestOut:
    ok = notify_contact_request(
        name=payload.name,
        phone=payload.phone,
        message=payload.message,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not send your message. Please try again in a moment.",
        )
    return ContactRequestOut()
