"""Admin Cashbook — /admin/cashbook (ledger, manual entries, accounting exports)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.cashbook import ONLINE, build_cashbook
from app.core.ist import today
from app.core.sales_export import build_sales_export
from app.database import get_db
from app.deps import TokenPrincipal, require_role
from app.dto.cashbook_dto import (
    IN_CATEGORIES,
    OUT_CATEGORIES,
    CashbookEntryCreate,
    CashbookEntryOut,
    CashbookResponse,
)
from app.dto.sales_export_dto import SalesExportResponse
from app.schemas import CashbookEntry, Store, User

router = APIRouter(
    prefix="/admin/cashbook",
    tags=["admin-cashbook"],
    dependencies=[Depends(require_role("admin"))],
)

MAX_EXPORT_DAYS = 92
MAX_LEDGER_DAYS = 366


def _check_range(date_from: date, date_to: date, max_days: int) -> None:
    if date_to < date_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_to must be on or after date_from.",
        )
    if (date_to - date_from).days + 1 > max_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Pick at most {max_days} days at a time.",
        )


@router.get("", response_model=CashbookResponse)
def cashbook(
    date_from: date = Query(...),
    date_to: date = Query(...),
    store: str = Query("all", description="'all', 'online' or a store id"),
    db: Session = Depends(get_db),
) -> CashbookResponse:
    _check_range(date_from, date_to, MAX_LEDGER_DAYS)
    key = store.strip().lower()
    if key in ("all", ONLINE):
        return build_cashbook(db, date_from, date_to, key)
    if not key.isdigit():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid store.")
    return build_cashbook(db, date_from, date_to, int(key))


@router.post("/entries", response_model=CashbookEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: CashbookEntryCreate,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("admin")),
) -> CashbookEntryOut:
    allowed = IN_CATEGORIES if payload.entry_type == "in" else OUT_CATEGORIES
    if payload.category not in allowed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown category.")
    if payload.entry_date > today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Date cannot be in the future."
        )
    store = db.get(Store, payload.store_id) if payload.store_id is not None else None
    if payload.store_id is not None and store is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found.")
    user = db.get(User, principal.sub)

    row = CashbookEntry(
        store_id=payload.store_id,
        entry_date=payload.entry_date,
        entry_type=payload.entry_type,
        category=payload.category,
        mode=payload.mode,
        amount=payload.amount,
        note=payload.note or None,
        entered_by_id=user.id if user else None,
        entered_by_name=user.name if user else "Admin",
    )
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return CashbookEntryOut(
        id=f"m-{row.id}",
        source="manual",
        store_id=row.store_id,
        store=store.name if store else "Online / Head office",
        date=row.entry_date.isoformat(),
        time=row.created_at.strftime("%H:%M") if row.created_at else "",
        type=row.entry_type,
        category=row.category,
        mode=row.mode,
        amount=float(row.amount),
        note=row.note or "",
        entered_by=row.entered_by_name or "",
    )


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, db: Session = Depends(get_db)) -> Response:
    row = db.get(CashbookEntry, entry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sales-export", response_model=SalesExportResponse)
def sales_export(
    date_from: date = Query(...),
    date_to: date = Query(...),
    db: Session = Depends(get_db),
) -> SalesExportResponse:
    """Invoice and credit-note lines for the Tally sales and GSTR-1 Excel exports.

    Unpaginated on purpose (it feeds a file download), so the range is capped instead.
    """
    _check_range(date_from, date_to, MAX_EXPORT_DAYS)
    return build_sales_export(db, date_from, date_to)
