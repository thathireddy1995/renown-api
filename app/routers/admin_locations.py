"""Admin unified locations — stores and warehouses as one CRUD list.

GET uses a single UNION query (no N+1). Writes go to the existing
`stores` / `warehouses` tables so POS, inventory, and staff login stay intact.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, String, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import pagination, require_role
from app.dto.location_dto import (
    AdminLocationCreate,
    AdminLocationListResponse,
    AdminLocationOut,
    AdminLocationUpdate,
)
from app.schemas import Store, User, Warehouse

router = APIRouter(
    prefix="/admin/locations",
    tags=["admin-locations"],
    dependencies=[Depends(require_role("admin"))],
)


def _store_status_default(raw: str | None) -> str:
    return (raw or "Open").strip() or "Open"


def _warehouse_status_default(raw: str | None) -> str:
    return (raw or "Active").strip() or "Active"


def _union_stmt():
    stores = select(
        literal("store").label("kind"),
        Store.id.label("id"),
        Store.code.label("code"),
        Store.name.label("name"),
        func.coalesce(Store.address, "").label("address"),
        func.coalesce(Store.city, "").label("city"),
        func.coalesce(Store.country, "").label("country"),
        Store.phone.label("phone"),
        func.coalesce(Store.status, "Open").label("status"),
        Store.warehouse_id.label("warehouse_id"),
    )
    warehouses = select(
        literal("warehouse").label("kind"),
        Warehouse.id.label("id"),
        Warehouse.code.label("code"),
        Warehouse.name.label("name"),
        func.coalesce(Warehouse.address, "").label("address"),
        func.coalesce(Warehouse.city, "").label("city"),
        func.coalesce(Warehouse.country, "").label("country"),
        literal(None).cast(String).label("phone"),
        func.coalesce(Warehouse.status, "Active").label("status"),
        literal(None).cast(Integer).label("warehouse_id"),
    )
    return union_all(stores, warehouses).subquery("locations")


def _apply_filters(stmt, loc, *, kind: str | None, search: str | None):
    if kind in ("store", "warehouse"):
        stmt = stmt.where(loc.c.kind == kind)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                loc.c.name.ilike(like),
                loc.c.code.ilike(like),
                loc.c.city.ilike(like),
                loc.c.address.ilike(like),
            )
        )
    return stmt


def _hydrate(db: Session, rows) -> list[AdminLocationOut]:
    store_ids = [int(r.id) for r in rows if r.kind == "store"]
    warehouse_ids = [int(r.id) for r in rows if r.kind == "warehouse"]
    managers: dict[tuple[str, int], str] = {}
    if store_ids:
        for sid, name in db.execute(
            select(User.store_id, User.name).where(
                User.store_id.in_(store_ids),
                User.role == "store_manager",
                User.is_active.is_(True),
            )
        ):
            if sid is not None and ("store", int(sid)) not in managers:
                managers[("store", int(sid))] = name
    if warehouse_ids:
        for wid, name in db.execute(
            select(User.warehouse_id, User.name).where(
                User.warehouse_id.in_(warehouse_ids),
                User.role == "warehouse_manager",
                User.is_active.is_(True),
            )
        ):
            if wid is not None and ("warehouse", int(wid)) not in managers:
                managers[("warehouse", int(wid))] = name

    items = []
    for r in rows:
        kind = str(r.kind)
        loc_id = int(r.id)
        items.append(
            AdminLocationOut(
                kind=kind,
                id=loc_id,
                location_id=f"{kind}:{loc_id}",
                code=r.code,
                name=r.name,
                address=r.address or "",
                city=r.city or "",
                country=r.country or "",
                phone=r.phone,
                status=r.status or "",
                warehouse_id=int(r.warehouse_id) if r.warehouse_id is not None else None,
                manager_name=managers.get((kind, loc_id)),
            )
        )
    return items


def _row_out_store(s: Store, manager_name: str | None = None) -> AdminLocationOut:
    return AdminLocationOut(
        kind="store",
        id=s.id,
        location_id=f"store:{s.id}",
        code=s.code,
        name=s.name,
        address=s.address or "",
        city=s.city or "",
        country=s.country or "",
        phone=s.phone,
        status=s.status or "Open",
        warehouse_id=s.warehouse_id,
        manager_name=manager_name,
    )


def _row_out_warehouse(w: Warehouse, manager_name: str | None = None) -> AdminLocationOut:
    return AdminLocationOut(
        kind="warehouse",
        id=w.id,
        location_id=f"warehouse:{w.id}",
        code=w.code,
        name=w.name,
        address=w.address or "",
        city=w.city or "",
        country=w.country or "",
        phone=None,
        status=w.status or "Active",
        warehouse_id=None,
        manager_name=manager_name,
    )


@router.get("", response_model=AdminLocationListResponse)
def list_locations(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
    kind: str | None = Query(None, description="store | warehouse"),
    search: str | None = Query(None, alias="q"),
) -> AdminLocationListResponse:
    limit, offset = page
    loc = _union_stmt()
    filtered = _apply_filters(select(loc), loc, kind=kind, search=search)
    total = db.scalar(_apply_filters(select(func.count()).select_from(loc), loc, kind=kind, search=search)) or 0
    rows = db.execute(
        filtered.order_by(loc.c.kind.asc(), loc.c.name.asc()).limit(limit).offset(offset)
    ).all()
    return AdminLocationListResponse(
        items=_hydrate(db, rows),
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AdminLocationOut, status_code=status.HTTP_201_CREATED)
def create_location(body: AdminLocationCreate, db: Session = Depends(get_db)) -> AdminLocationOut:
    kind = (body.kind or "").strip().lower()
    code = (body.code or "").strip()
    name = (body.name or "").strip()
    if kind not in ("store", "warehouse"):
        raise HTTPException(status_code=400, detail="kind must be store or warehouse")
    if not code or not name:
        raise HTTPException(status_code=400, detail="code and name are required")

    if kind == "store":
        if db.scalar(select(Store.id).where(Store.code == code)):
            raise HTTPException(status_code=409, detail="Store code already exists")
        if body.warehouse_id and not db.get(Warehouse, body.warehouse_id):
            raise HTTPException(status_code=400, detail="Warehouse not found")
        row = Store(
            code=code,
            name=name,
            address=(body.address or "").strip() or None,
            city=(body.city or "").strip() or None,
            country=(body.country or "India").strip() or "India",
            phone=(body.phone or "").strip() or None,
            status=_store_status_default(body.status),
            warehouse_id=body.warehouse_id,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _row_out_store(row)

    if db.scalar(select(Warehouse.id).where(Warehouse.code == code)):
        raise HTTPException(status_code=409, detail="Warehouse code already exists")
    row = Warehouse(
        code=code,
        name=name,
        address=(body.address or "").strip() or None,
        city=(body.city or "").strip() or None,
        country=(body.country or "India").strip() or "India",
        status=_warehouse_status_default(body.status),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _row_out_warehouse(row)


@router.get("/{kind}/{location_id}", response_model=AdminLocationOut)
def get_location(kind: str, location_id: int, db: Session = Depends(get_db)) -> AdminLocationOut:
    kind = kind.strip().lower()
    if kind == "store":
        row = db.get(Store, location_id)
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
        return _row_out_store(row)
    if kind == "warehouse":
        row = db.get(Warehouse, location_id)
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
        return _row_out_warehouse(row)
    raise HTTPException(status_code=400, detail="kind must be store or warehouse")


@router.patch("/{kind}/{location_id}", response_model=AdminLocationOut)
def update_location(
    kind: str,
    location_id: int,
    body: AdminLocationUpdate,
    db: Session = Depends(get_db),
) -> AdminLocationOut:
    kind = kind.strip().lower()
    data = body.model_dump(exclude_unset=True)
    if kind == "store":
        row = db.get(Store, location_id)
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
        if "code" in data and data["code"]:
            taken = db.scalar(select(Store.id).where(Store.code == data["code"].strip(), Store.id != row.id))
            if taken:
                raise HTTPException(status_code=409, detail="Store code already exists")
            row.code = data["code"].strip()
        if "name" in data and data["name"]:
            row.name = data["name"].strip()
        if "address" in data:
            row.address = (data["address"] or "").strip() or None
        if "city" in data:
            row.city = (data["city"] or "").strip() or None
        if "country" in data:
            row.country = (data["country"] or "").strip() or None
        if "phone" in data:
            row.phone = (data["phone"] or "").strip() or None
        if "status" in data and data["status"]:
            row.status = data["status"].strip()
        if "warehouse_id" in data:
            if data["warehouse_id"] and not db.get(Warehouse, data["warehouse_id"]):
                raise HTTPException(status_code=400, detail="Warehouse not found")
            row.warehouse_id = data["warehouse_id"]
        db.commit()
        db.refresh(row)
        return _row_out_store(row)

    if kind == "warehouse":
        row = db.get(Warehouse, location_id)
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
        if "code" in data and data["code"]:
            taken = db.scalar(
                select(Warehouse.id).where(Warehouse.code == data["code"].strip(), Warehouse.id != row.id)
            )
            if taken:
                raise HTTPException(status_code=409, detail="Warehouse code already exists")
            row.code = data["code"].strip()
        if "name" in data and data["name"]:
            row.name = data["name"].strip()
        if "address" in data:
            row.address = (data["address"] or "").strip() or None
        if "city" in data:
            row.city = (data["city"] or "").strip() or None
        if "country" in data:
            row.country = (data["country"] or "").strip() or None
        if "status" in data and data["status"]:
            row.status = data["status"].strip()
        db.commit()
        db.refresh(row)
        return _row_out_warehouse(row)

    raise HTTPException(status_code=400, detail="kind must be store or warehouse")


@router.delete("/{kind}/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(kind: str, location_id: int, db: Session = Depends(get_db)) -> None:
    kind = kind.strip().lower()
    if kind == "store":
        row = db.get(Store, location_id)
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
        tagged = db.scalar(
            select(func.count()).select_from(User).where(User.store_id == location_id, User.is_active.is_(True))
        ) or 0
        if tagged:
            raise HTTPException(status_code=409, detail="Unassign store managers before deleting this location")
        db.delete(row)
        db.commit()
        return
    if kind == "warehouse":
        row = db.get(Warehouse, location_id)
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
        tagged = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.warehouse_id == location_id, User.is_active.is_(True))
        ) or 0
        if tagged:
            raise HTTPException(status_code=409, detail="Unassign warehouse managers before deleting this location")
        linked = db.scalar(select(func.count()).select_from(Store).where(Store.warehouse_id == location_id)) or 0
        if linked:
            raise HTTPException(status_code=409, detail="Unlink stores from this warehouse before deleting")
        db.delete(row)
        db.commit()
        return
    raise HTTPException(status_code=400, detail="kind must be store or warehouse")
