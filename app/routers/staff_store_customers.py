"""Staff store customers — /staff/store/customers."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import pagination, require_role
from app.schemas import Customer, Order

router = APIRouter(
    prefix="/staff/store/customers",
    tags=["staff-store-customers"],
    dependencies=[Depends(require_role("store_manager"))],
)


class StaffCustomerOut(BaseModel):
    id: str
    name: str
    phone: str
    email: str
    visits: int
    spent: str
    tier: str


class StaffCustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=20)
    email: str | None = None
    tier: str | None = None


class StaffCustomerListResponse(BaseModel):
    items: list[StaffCustomerOut]
    total: int
    limit: int
    offset: int


def _digits(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _format_phone(phone: str) -> str:
    d = _digits(phone)
    if len(d) == 10:
        return f"+91 {d[:5]} {d[5:]}"
    if len(d) == 12 and d.startswith("91"):
        return f"+91 {d[2:7]} {d[7:]}"
    return phone.strip()


def _format_inr(amount: float) -> str:
    return f"₹{amount:,.0f}"


def _tier_from_spent(spent: float, preferred: str | None = None) -> str:
    if preferred in ("Bronze", "Silver", "Gold", "Platinum"):
        return preferred
    if spent >= 50000:
        return "Platinum"
    if spent >= 25000:
        return "Gold"
    if spent >= 10000:
        return "Silver"
    return "Bronze"


def _order_stats_subq():
    return (
        select(
            Order.customer_id.label("customer_id"),
            func.count(Order.id).label("visits"),
            func.coalesce(func.sum(Order.total), 0).label("spent"),
        )
        .group_by(Order.customer_id)
        .subquery()
    )


def _row(customer: Customer, visits: int | None, spent) -> StaffCustomerOut:
    spent_f = float(spent or 0)
    return StaffCustomerOut(
        id=f"C-{customer.id}",
        name=customer.name or f"Customer {customer.phone[-4:]}",
        phone=_format_phone(customer.phone),
        email=customer.email or "—",
        visits=int(visits or 0),
        spent=_format_inr(spent_f),
        tier=_tier_from_spent(spent_f),
    )


@router.get("", response_model=StaffCustomerListResponse)
def list_customers(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> StaffCustomerListResponse:
    limit, offset = page
    stats = _order_stats_subq()

    stmt = (
        select(Customer, stats.c.visits, stats.c.spent)
        .outerjoin(stats, stats.c.customer_id == Customer.id)
        .where(Customer.is_active.is_(True))
    )
    count_stmt = (
        select(func.count()).select_from(Customer).where(Customer.is_active.is_(True))
    )

    if search and search.strip():
        like = f"%{search.strip()}%"
        filt = or_(
            Customer.name.ilike(like),
            Customer.email.ilike(like),
            Customer.phone.ilike(like),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(Customer.created_at.desc(), Customer.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return StaffCustomerListResponse(
        items=[_row(c, visits, spent) for c, visits, spent in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=StaffCustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    body: StaffCustomerCreate,
    db: Session = Depends(get_db),
) -> StaffCustomerOut:
    phone = _digits(body.phone)
    if len(phone) < 10:
        raise HTTPException(status_code=422, detail="Enter a valid phone number")

    existing = db.scalar(select(Customer).where(Customer.phone == phone))
    if existing:
        # Update profile and return existing row so add is idempotent.
        if body.name.strip():
            existing.name = body.name.strip()
        if body.email and body.email.strip():
            existing.email = body.email.strip()
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return _row(existing, 0, 0)

    # Also match walk-in style store orders by phone suffix later; create clean CRM row.
    customer = Customer(
        name=body.name.strip(),
        phone=phone,
        email=(body.email or "").strip() or None,
        is_active=True,
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Prefer requested tier for brand-new customers with no spend yet.
    out = _row(customer, 0, 0)
    if body.tier in ("Bronze", "Silver", "Gold", "Platinum"):
        out = out.model_copy(update={"tier": body.tier})
    return out
