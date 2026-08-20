"""Admin coupons CRUD under /admin/coupons."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_staff, pagination, require_role
from app.dto.coupons_dto import (
    CouponCreate,
    CouponListResponse,
    CouponOut,
    CouponUpdate,
)
from app.schemas import Brand, Category, Coupon, User

router = APIRouter(
    prefix="/admin/coupons",
    tags=["admin-coupons"],
    dependencies=[Depends(require_role("admin"))],
)


def _load_coupon(db: Session, coupon_id: int) -> Coupon | None:
    return db.scalar(
        select(Coupon)
        .where(Coupon.id == coupon_id)
        .options(selectinload(Coupon.brand), selectinload(Coupon.category))
    )


def _status_for_dates(start_date: datetime, end_date: datetime) -> str:
    now = datetime.now(timezone.utc)
    start = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
    end = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
    if now < start:
        return "scheduled"
    if now > end:
        return "expired"
    return "active"


def _display_status(coupon: Coupon) -> str:
    if coupon.status in ("inactive", "deleted"):
        return coupon.status
    return _status_for_dates(coupon.start_date, coupon.end_date)


def _coupon_out(coupon: Coupon) -> CouponOut:
    return CouponOut(
        id=coupon.id,
        name=coupon.name,
        code=coupon.code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        maximum_discount=coupon.maximum_discount,
        min_order_amount=coupon.min_order_amount or 0,
        apply_on=coupon.apply_on,
        brand_id=coupon.brand_id,
        brand_name=coupon.brand.name if coupon.brand else None,
        category_id=coupon.category_id,
        category_name=coupon.category.name if coupon.category else None,
        gender=coupon.gender,
        start_date=coupon.start_date,
        end_date=coupon.end_date,
        usage_limit=coupon.usage_limit,
        per_customer_limit=coupon.per_customer_limit,
        used_count=coupon.used_count or 0,
        status=_display_status(coupon),
        created_at=coupon.created_at,
        updated_at=coupon.updated_at,
    )


def _normalize_target(data: dict, db: Session) -> None:
    apply_on = data["apply_on"]
    if apply_on == "ALL":
        data["brand_id"] = None
        data["category_id"] = None
        data["gender"] = None
        return

    target_fields = {
        "BRAND": "brand_id",
        "CATEGORY": "category_id",
        "GENDER": "gender",
    }
    target_field = target_fields[apply_on]
    if not data.get(target_field):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{target_field.replace('_', ' ').title()} is required.",
        )

    if target_field == "brand_id" and db.get(Brand, data["brand_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected brand does not exist.",
        )
    if target_field == "category_id" and db.get(Category, data["category_id"]) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Selected category does not exist.",
        )

    if apply_on == "GENDER":
        gender = (data.get("gender") or "").strip().upper()
        if gender not in ("MALE", "FEMALE", "UNISEX", "KIDS"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Gender must be Men, Women, Unisex, or Kids.",
            )
        data["gender"] = gender

    for field in ("brand_id", "category_id", "gender"):
        if field != target_field:
            data[field] = None

    if data["discount_type"] == "FLAT":
        data["maximum_discount"] = None


def _code_taken(db: Session, code: str, exclude_id: int | None = None) -> bool:
    stmt = select(Coupon.id).where(Coupon.code == code, Coupon.status != "deleted")
    if exclude_id is not None:
        stmt = stmt.where(Coupon.id != exclude_id)
    return db.scalar(stmt) is not None


@router.get("/", response_model=CouponListResponse)
def list_coupons(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    status_filter: str | None = Query(None, alias="status"),
    search: str | None = Query(None, alias="q"),
) -> CouponListResponse:
    limit, offset = page
    stmt = select(Coupon).where(Coupon.status != "deleted")
    count_stmt = select(func.count()).select_from(Coupon).where(Coupon.status != "deleted")

    if status_filter and status_filter != "all":
        if status_filter == "inactive":
            status_clause = Coupon.status == "inactive"
        elif status_filter == "scheduled":
            status_clause = (Coupon.status != "inactive") & (Coupon.start_date > func.now())
        elif status_filter == "active":
            status_clause = (
                (Coupon.status != "inactive")
                & (Coupon.start_date <= func.now())
                & (Coupon.end_date >= func.now())
            )
        elif status_filter == "expired":
            status_clause = (Coupon.status != "inactive") & (Coupon.end_date < func.now())
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid coupon status filter.",
            )
        stmt = stmt.where(status_clause)
        count_stmt = count_stmt.where(status_clause)

    if search:
        like = f"%{search.strip()}%"
        filt = or_(Coupon.name.ilike(like), Coupon.code.ilike(like))
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.options(selectinload(Coupon.brand), selectinload(Coupon.category))
        .order_by(Coupon.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return CouponListResponse(
        items=[_coupon_out(c) for c in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{coupon_id}", response_model=CouponOut)
def get_coupon(coupon_id: int, db: Session = Depends(get_db)) -> CouponOut:
    coupon = _load_coupon(db, coupon_id)
    if not coupon or coupon.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found.")
    return _coupon_out(coupon)


@router.post("/", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
def create_coupon(
    payload: CouponCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> CouponOut:
    if payload.end_date <= payload.start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="End date must be after start date.",
        )
    if payload.discount_type == "PERCENTAGE" and payload.discount_value > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Discount value cannot exceed 100% for percentage coupons.",
        )
    if _code_taken(db, payload.code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A coupon with this code already exists.",
        )

    data = payload.model_dump()
    _normalize_target(data, db)

    coupon = Coupon(
        name=data["name"],
        code=data["code"],
        discount_type=data["discount_type"],
        discount_value=data["discount_value"],
        maximum_discount=data["maximum_discount"],
        min_order_amount=data["min_order_amount"] or 0,
        apply_on=data["apply_on"],
        brand_id=data["brand_id"],
        category_id=data["category_id"],
        gender=data["gender"],
        start_date=data["start_date"],
        end_date=data["end_date"],
        usage_limit=data["usage_limit"],
        per_customer_limit=data["per_customer_limit"],
        used_count=0,
        status=_status_for_dates(data["start_date"], data["end_date"]),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(coupon)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A coupon with this code already exists.",
        ) from err
    except DataError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid data for coupon fields. {err.orig}",
        ) from err

    coupon = _load_coupon(db, coupon.id)
    assert coupon is not None
    return _coupon_out(coupon)


@router.patch("/{coupon_id}", response_model=CouponOut)
def update_coupon(
    coupon_id: int,
    payload: CouponUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> CouponOut:
    coupon = _load_coupon(db, coupon_id)
    if not coupon or coupon.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found.")

    data = payload.model_dump(exclude_unset=True)
    if "code" in data and data["code"] and _code_taken(db, data["code"], exclude_id=coupon.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A coupon with this code already exists.",
        )

    start_date = data.get("start_date", coupon.start_date)
    end_date = data.get("end_date", coupon.end_date)
    if end_date <= start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="End date must be after start date.",
        )

    discount_type = data.get("discount_type", coupon.discount_type)
    discount_value = data.get("discount_value", coupon.discount_value)
    if discount_type == "PERCENTAGE" and discount_value > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Discount value cannot exceed 100% for percentage coupons.",
        )

    target_data = {
        "apply_on": data.get("apply_on", coupon.apply_on),
        "brand_id": data.get("brand_id", coupon.brand_id),
        "category_id": data.get("category_id", coupon.category_id),
        "gender": data.get("gender", coupon.gender),
        "discount_type": discount_type,
        "maximum_discount": data.get("maximum_discount", coupon.maximum_discount),
    }
    _normalize_target(target_data, db)
    data.update(target_data)

    for key, value in data.items():
        if hasattr(coupon, key):
            setattr(coupon, key, value)
    coupon.updated_by = actor.id
    if coupon.status != "inactive":
        coupon.status = _status_for_dates(start_date, end_date)

    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A coupon with this code already exists.",
        ) from err

    coupon = _load_coupon(db, coupon.id)
    assert coupon is not None
    return _coupon_out(coupon)


@router.delete("/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> None:
    coupon = db.get(Coupon, coupon_id)
    if not coupon or coupon.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found.")

    suffix = f"-DEL{coupon.id}"
    coupon.status = "deleted"
    coupon.updated_by = actor.id
    if not coupon.code.endswith(suffix):
        coupon.code = f"{coupon.code[: max(1, 30 - len(suffix))]}{suffix}"[:30]
    db.commit()


@router.post("/{coupon_id}/activate", response_model=CouponOut)
def activate_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> CouponOut:
    coupon = _load_coupon(db, coupon_id)
    if not coupon or coupon.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found.")
    coupon.status = _status_for_dates(coupon.start_date, coupon.end_date)
    coupon.updated_by = actor.id
    db.commit()
    coupon = _load_coupon(db, coupon.id)
    assert coupon is not None
    return _coupon_out(coupon)


@router.post("/{coupon_id}/deactivate", response_model=CouponOut)
def deactivate_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_staff),
) -> CouponOut:
    coupon = _load_coupon(db, coupon_id)
    if not coupon or coupon.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coupon not found.")
    coupon.status = "inactive"
    coupon.updated_by = actor.id
    db.commit()
    coupon = _load_coupon(db, coupon.id)
    assert coupon is not None
    return _coupon_out(coupon)
