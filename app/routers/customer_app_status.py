"""Public mobile app status (maintenance mode + live offer summary)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.core.company_settings import app_status_public
from app.core.ist import IST_SQL_NOW, as_ist
from app.database import get_db
from app.schemas import Offer

router = APIRouter(prefix="/customer", tags=["customer-app"])


def _offer_summary(db: Session) -> dict[str, object]:
    live = (
        Offer.status.notin_(("inactive", "deleted")),
        Offer.start_date <= IST_SQL_NOW,
        Offer.end_date >= IST_SQL_NOW,
    )
    try:
        max_percent, ends_at = db.execute(
            select(
                func.max(Offer.discount_value).filter(Offer.discount_type == "PERCENTAGE"),
                func.min(Offer.end_date),
            ).where(*live)
        ).one()
    except ProgrammingError:
        db.rollback()
        return {"offers_max_percent": None, "offers_ends_at": None}
    return {
        "offers_max_percent": int(max_percent) if max_percent else None,
        "offers_ends_at": as_ist(ends_at).isoformat() if ends_at else None,
    }


@router.get("/app-status")
def get_app_status(db: Session = Depends(get_db)) -> dict[str, object]:
    return {**app_status_public(db), **_offer_summary(db)}
