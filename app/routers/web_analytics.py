"""Public storefront tracker ingest."""

from fastapi import APIRouter, Depends, Request

from app.core.web_analytics import record_event
from app.database import get_db
from app.dto.web_analytics_dto import TrackAnalyticsIn, TrackAnalyticsOut
from sqlalchemy.orm import Session

router = APIRouter(tags=["web-analytics"])


@router.post("/customer/page-hit", response_model=TrackAnalyticsOut)
@router.post("/analytics/track", response_model=TrackAnalyticsOut)
def track_event(
    payload: TrackAnalyticsIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TrackAnalyticsOut:
    record_event(
        db,
        request,
        event_name=payload.event_name,
        path=payload.path,
        referrer=payload.referrer,
        timezone_name=payload.timezone,
        anonymous_id=payload.visitor_id,
        client_session_id=payload.session_id,
        metadata=payload.metadata,
    )
    return TrackAnalyticsOut()
