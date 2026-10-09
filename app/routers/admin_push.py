"""Push sending — /admin/push (admin JWT) and /dev/push (non-production only)."""

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import S3_PUBLIC_BUCKET
from app.core.deps import TokenPrincipal, require_role
from app.core.push import PushNotConfigured, PushTokenInvalid, send_to_token
from app.core.s3_images import presign_push_image_puts
from app.database import get_db
from app.dto.catalog_dto import ImagePresignItem, ImagePresignRequest, ImagePresignResponse
from app.dto.push_dto import (
    PushLogListResponse,
    PushLogOut,
    PushRecipientListResponse,
    PushRecipientOut,
    PushSendResult,
    PushStatsOut,
    PushTestRequest,
)
from app.schemas import Customer, CustomerPushToken, PushNotificationLog

_admin = require_role("admin")

router = APIRouter(
    prefix="/admin/push",
    tags=["admin-push"],
    dependencies=[Depends(_admin)],
)
dev_router = APIRouter(prefix="/dev/push", tags=["dev-push"])

# FCM HTTP v1 has no multicast; fan out in parallel but stay well under the
# 29s API Gateway timeout.
_SEND_WORKERS = 16


def _resolve_audience(payload: PushTestRequest) -> str:
    if payload.audience:
        return payload.audience
    return "token" if payload.token else "customer"


def _target_tokens(payload: PushTestRequest, audience: str, db: Session) -> list[str]:
    if audience == "token":
        if not payload.token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide token.")
        return [payload.token]
    if audience == "customer":
        if payload.customer_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide customer_id.")
        tokens = list(
            db.scalars(
                select(CustomerPushToken.token).where(
                    CustomerPushToken.customer_id == payload.customer_id
                )
            ).all()
        )
        if not tokens:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer has no registered devices.")
        return tokens
    tokens = list(db.scalars(select(CustomerPushToken.token)).all())
    if not tokens:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No customer devices are registered yet.")
    return tokens


def _send(
    payload: PushTestRequest, db: Session, actor_id: int | None = None
) -> PushSendResult:
    audience = _resolve_audience(payload)
    tokens = _target_tokens(payload, audience, db)

    log: PushNotificationLog | None = None
    data = dict(payload.data or {})
    if audience != "token":
        log = PushNotificationLog(
            title=payload.title,
            body=payload.body,
            image_url=payload.image,
            audience=audience,
            customer_id=payload.customer_id if audience == "customer" else None,
            sent=0,
            failed=0,
            created_by=actor_id,
        )
        db.add(log)
        db.flush()
        data["notification_id"] = str(log.id)

    def _one(token: str) -> tuple[str, str | None, bool]:
        try:
            send_to_token(token, payload.title, payload.body, data or None, payload.image)
            return token, None, False
        except PushTokenInvalid as exc:
            return token, str(exc), True
        except PushNotConfigured:
            raise
        except Exception as exc:
            return token, str(exc), False

    try:
        with ThreadPoolExecutor(max_workers=min(_SEND_WORKERS, len(tokens))) as pool:
            results = list(pool.map(_one, tokens))
    except PushNotConfigured as exc:
        db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))

    errors = [err for _, err, _ in results if err]
    sent = len(results) - len(errors)
    dead = [tok for tok, _, invalid in results if invalid] if audience != "token" else []

    if dead:
        db.execute(delete(CustomerPushToken).where(CustomerPushToken.token.in_(dead)))
    if log is not None:
        log.sent = sent
        log.failed = len(errors)
    if dead or log is not None:
        db.commit()
    return PushSendResult(sent=sent, failed=len(errors), removed=len(dead), errors=errors[:10])


@router.post("/send", response_model=PushSendResult)
def admin_send_push(
    payload: PushTestRequest,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(_admin),
) -> PushSendResult:
    return _send(payload, db, principal.sub)


@router.get("/stats", response_model=PushStatsOut)
def admin_push_stats(db: Session = Depends(get_db)) -> PushStatsOut:
    devices, customers = db.execute(
        select(
            func.count(CustomerPushToken.id),
            func.count(func.distinct(CustomerPushToken.customer_id)),
        )
    ).one()
    return PushStatsOut(devices=devices or 0, customers=customers or 0)


@router.get("/recipients", response_model=PushRecipientListResponse)
def admin_push_recipients(
    q: str | None = Query(default=None, max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> PushRecipientListResponse:
    stmt = (
        select(
            Customer.id,
            Customer.name,
            Customer.phone,
            Customer.email,
            func.count(CustomerPushToken.id).label("devices"),
        )
        .join(CustomerPushToken, CustomerPushToken.customer_id == Customer.id)
        .group_by(Customer.id)
        .order_by(func.max(CustomerPushToken.updated_at).desc())
        .limit(limit)
    )
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        conds = [
            Customer.name.ilike(like),
            Customer.phone.ilike(like),
            Customer.email.ilike(like),
        ]
        if term.isdigit():
            conds.append(Customer.id == int(term))
        stmt = stmt.where(or_(*conds))
    rows = db.execute(stmt).all()
    return PushRecipientListResponse(
        items=[
            PushRecipientOut(id=r.id, name=r.name, phone=r.phone, email=r.email, devices=r.devices)
            for r in rows
        ]
    )


@router.get("/history", response_model=PushLogListResponse)
def admin_push_history(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> PushLogListResponse:
    rows = db.execute(
        select(PushNotificationLog, Customer.name)
        .outerjoin(Customer, Customer.id == PushNotificationLog.customer_id)
        .order_by(PushNotificationLog.created_at.desc())
        .limit(limit)
    ).all()
    items = []
    for log, customer_name in rows:
        out = PushLogOut.model_validate(log)
        out.customer_name = customer_name
        items.append(out)
    return PushLogListResponse(items=items)


@router.post("/image/presign", response_model=ImagePresignResponse)
def admin_push_image_presign(payload: ImagePresignRequest) -> ImagePresignResponse:
    if len(payload.files) != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Select exactly one image.")
    uploads = presign_push_image_puts([(f.filename, f.content_type) for f in payload.files])
    return ImagePresignResponse(
        bucket=S3_PUBLIC_BUCKET,
        uploads=[ImagePresignItem(**item) for item in uploads],
    )


@dev_router.post("/test", response_model=PushSendResult)
def dev_send_push(payload: PushTestRequest, db: Session = Depends(get_db)) -> PushSendResult:
    return _send(payload, db)
