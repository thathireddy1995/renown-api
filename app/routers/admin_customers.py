"""Admin customers — /admin/customers."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.admin_order_status import admin_status_label
from app.database import get_db
from app.deps import pagination
from app.dto.admin_dto import (
    AdminCustomerDetailOut,
    AdminCustomerListResponse,
    AdminCustomerOut,
    AdminOrderOut,
)
from app.schemas import Customer, Order

router = APIRouter(prefix="/admin/customers", tags=["admin-customers"])


def _order_stats_subq():
    return (
        select(
            Order.customer_id.label("customer_id"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total), 0).label("spent"),
            func.max(Order.created_at).label("last_order"),
        )
        .group_by(Order.customer_id)
        .subquery()
    )


def _customer_row(
    customer: Customer,
    orders: int | None,
    spent,
    last_order,
) -> AdminCustomerOut:
    last = ""
    if last_order is not None:
        last = last_order.strftime("%Y-%m-%d") if hasattr(last_order, "strftime") else str(last_order)[:10]
    return AdminCustomerOut(
        id=f"C-{customer.id:03d}" if customer.id < 1000 else f"C-{customer.id}",
        name=customer.name or f"Customer {customer.phone[-4:]}",
        email=customer.email or "",
        orders=int(orders or 0),
        spent=float(spent or 0),
        lastOrder=last,
    )


@router.get("", response_model=AdminCustomerListResponse)
def list_customers(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> AdminCustomerListResponse:
    limit, offset = page
    stats = _order_stats_subq()

    stmt = (
        select(
            Customer,
            stats.c.orders,
            stats.c.spent,
            stats.c.last_order,
        )
        .outerjoin(stats, stats.c.customer_id == Customer.id)
    )
    count_stmt = select(func.count()).select_from(Customer)

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

    return AdminCustomerListResponse(
        items=[
            _customer_row(customer, orders, spent, last_order)
            for customer, orders, spent, last_order in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{customer_id}", response_model=AdminCustomerDetailOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> AdminCustomerDetailOut:
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found"
        )

    stats = db.execute(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total), 0),
            func.max(Order.created_at),
        ).where(Order.customer_id == customer.id)
    ).one()
    orders_count, spent, last_order = stats

    recent = db.scalars(
        select(Order)
        .where(Order.customer_id == customer.id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(20)
    ).all()

    base = _customer_row(customer, orders_count, spent, last_order)
    recent_orders = [
        AdminOrderOut(
            id=o.order_number,
            customer=base.name,
            date=o.created_at.strftime("%Y-%m-%d") if o.created_at else "",
            items=len(o.items or []),
            status=admin_status_label(o.status),
            total=float(o.total or 0),
        )
        for o in recent
    ]

    return AdminCustomerDetailOut(
        **base.model_dump(),
        phone=customer.phone,
        is_active=customer.is_active,
        created_at=customer.created_at.strftime("%Y-%m-%d") if customer.created_at else "",
        recent_orders=recent_orders,
    )
