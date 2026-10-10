"""Admin-managed mobile app home sections and their public feed."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.catalog_serialize import product_cards_out
from app.database import get_db
from app.deps import require_role
from app.dto.home_sections_dto import (
    AdminHomeSectionOut,
    CustomerHomeSectionOut,
    CustomerHomeSectionsResponse,
    HomeSectionTileOut,
    HomeSectionUpdate,
)
from app.routers.customer_products import _CARD_LOAD
from app.schemas import Brand, Category, HomeSection, Product

admin_router = APIRouter(
    prefix="/admin/home-sections",
    tags=["admin-home-sections"],
    dependencies=[Depends(require_role("admin"))],
)
customer_router = APIRouter(prefix="/customer/home-sections", tags=["customer-home-sections"])

_MODEL = {"product": Product, "brand": Brand, "category": Category}


def _item_entries(section: HomeSection) -> list[dict]:
    out = []
    for raw in section.items or []:
        if isinstance(raw, dict) and isinstance(raw.get("id"), int):
            out.append(raw)
    return out


def _rows_by_id(db: Session, section: HomeSection, ids: list[int], active_only: bool) -> dict:
    if not ids:
        return {}
    model = _MODEL[section.item_type]
    stmt = select(model).where(model.id.in_(ids))
    if active_only:
        stmt = stmt.where(model.status == "active")
    if model is Product:
        stmt = stmt.options(*(_CARD_LOAD if active_only else (selectinload(Product.images),)))
    return {row.id: row for row in db.scalars(stmt).all()}


def _tile(row, entry: dict) -> HomeSectionTileOut:
    if isinstance(row, Product):
        image = row.images[0].url if row.images else ""
    else:
        image = row.image or ""
    return HomeSectionTileOut(
        id=row.id,
        slug=row.slug,
        name=row.name,
        image=image,
        label=str(entry.get("label") or ""),
        sublabel=str(entry.get("sublabel") or ""),
    )


def _ordered_sections(db: Session) -> list[HomeSection]:
    return list(
        db.scalars(select(HomeSection).order_by(HomeSection.sort_order, HomeSection.key)).all()
    )


def _admin_out(db: Session, section: HomeSection) -> AdminHomeSectionOut:
    entries = _item_entries(section)
    rows = _rows_by_id(db, section, [e["id"] for e in entries], active_only=False)
    return AdminHomeSectionOut(
        key=section.key,
        title=section.title,
        subtitle=section.subtitle or "",
        item_type=section.item_type,
        enabled=section.enabled,
        items=[_tile(rows[e["id"]], e) for e in entries if e["id"] in rows],
    )


@admin_router.get("", response_model=list[AdminHomeSectionOut])
def list_admin_home_sections(db: Session = Depends(get_db)) -> list[AdminHomeSectionOut]:
    return [_admin_out(db, s) for s in _ordered_sections(db)]


@admin_router.put("/{key}", response_model=AdminHomeSectionOut)
def update_home_section(
    key: str,
    payload: HomeSectionUpdate,
    db: Session = Depends(get_db),
) -> AdminHomeSectionOut:
    section = db.get(HomeSection, key)
    if section is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found.")

    seen: set[int] = set()
    items = []
    for item in payload.items:
        if item.id in seen:
            continue
        seen.add(item.id)
        items.append(item.model_dump())
    known = _rows_by_id(db, section, list(seen), active_only=False)
    missing = seen - known.keys()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown {section.item_type} id(s): {sorted(missing)}",
        )

    section.title = payload.title
    section.subtitle = payload.subtitle
    section.enabled = payload.enabled
    section.items = items
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(section)
    return _admin_out(db, section)


@customer_router.get(
    "",
    response_model=CustomerHomeSectionsResponse,
    response_model_exclude={
        "sections": {
            "__all__": {
                "products": {
                    "__all__": {"buying_price", "buyingPrice", "view_360_key", "view360Key"}
                }
            }
        }
    },
)
def list_customer_home_sections(db: Session = Depends(get_db)) -> CustomerHomeSectionsResponse:
    out = []
    for section in _ordered_sections(db):
        entries = _item_entries(section) if section.enabled else []
        rows = _rows_by_id(db, section, [e["id"] for e in entries], active_only=True)
        ordered = [(rows[e["id"]], e) for e in entries if e["id"] in rows]
        products = (
            product_cards_out(db, [row for row, _ in ordered])
            if section.item_type == "product"
            else []
        )
        tiles = [] if section.item_type == "product" else [_tile(row, e) for row, e in ordered]
        out.append(
            CustomerHomeSectionOut(
                key=section.key,
                title=section.title,
                subtitle=section.subtitle or "",
                item_type=section.item_type,
                enabled=section.enabled,
                products=products,
                tiles=tiles,
            )
        )
    return CustomerHomeSectionsResponse(sections=out)
