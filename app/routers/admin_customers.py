"""Admin customers — /admin/customers."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.admin_order_status import admin_status_label
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.admin_dto import (
    AdminCustomerDetailOut,
    AdminCustomerListResponse,
    AdminCustomerOut,
    AdminOrderOut,
)
from app.schemas import Customer, Order

router = APIRouter(prefix="/admin/customers", tags=["admin-customers"], dependencies=[Depends(require_role("admin"))])


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


def _customer_out(
    *,
    customer_id: int,
    name: str | None,
    email: str | None,
    phone: str | None,
    orders: int | None,
    spent,
    last_order,
) -> AdminCustomerOut:
    last = ""
    if last_order is not None:
        last = last_order.strftime("%Y-%m-%d") if hasattr(last_order, "strftime") else str(last_order)[:10]
    return AdminCustomerOut(
        id=f"C-{customer_id:03d}" if customer_id < 1000 else f"C-{customer_id}",
        name=name
        or (f"Customer {phone[-4:]}" if phone else None)
        or (email.split("@")[0].title() if email else "Customer"),
        email=email or "",
        orders=int(orders or 0),
        spent=float(spent or 0),
        lastOrder=last,
    )


def _customer_row(
    customer: Customer,
    orders: int | None,
    spent,
    last_order,
) -> AdminCustomerOut:
    return _customer_out(
        customer_id=customer.id,
        name=customer.name,
        email=customer.email,
        phone=customer.phone,
        orders=orders,
        spent=spent,
        last_order=last_order,
    )


@router.get("", response_model=AdminCustomerListResponse)
def list_customers(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    search: str | None = Query(None, alias="q"),
) -> AdminCustomerListResponse:
    limit, offset = page
    stats = _order_stats_subq()

    # One round-trip: page rows + total via window count. Avoids a separate
    # COUNT(*) against a high-RTT remote DB, and skips password_hash.
    stmt = (
        select(
            Customer.id,
            Customer.name,
            Customer.email,
            Customer.phone,
            stats.c.orders,
            stats.c.spent,
            stats.c.last_order,
            func.count().over().label("total_count"),
        )
        .select_from(Customer)
        .outerjoin(stats, stats.c.customer_id == Customer.id)
    )

    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Customer.name.ilike(like),
                Customer.email.ilike(like),
                Customer.phone.ilike(like),
            )
        )

    rows = db.execute(
        stmt.order_by(Customer.created_at.desc(), Customer.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    total = int(rows[0].total_count) if rows else 0
    if not rows and offset > 0:
        count_stmt = select(func.count()).select_from(Customer)
        if search and search.strip():
            like = f"%{search.strip()}%"
            count_stmt = count_stmt.where(
                or_(
                    Customer.name.ilike(like),
                    Customer.email.ilike(like),
                    Customer.phone.ilike(like),
                )
            )
        total = db.scalar(count_stmt) or 0

    return AdminCustomerListResponse(
        items=[
            _customer_out(
                customer_id=row.id,
                name=row.name,
                email=row.email,
                phone=row.phone,
                orders=row.orders,
                spent=row.spent,
                last_order=row.last_order,
            )
            for row in rows
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
