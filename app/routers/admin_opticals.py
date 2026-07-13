"""Admin opticals CRUD — /admin/opticals/{lens-types,frame-types,colors,sizes}."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.taxonomy_utils import public_id
from app.database import get_db
from app.deps import pagination, require_role
from app.dto.taxonomy_dto import (
    ColorCreate,
    ColorListResponse,
    ColorOut,
    ColorUpdate,
    FrameTypeCreate,
    FrameTypeListResponse,
    FrameTypeOut,
    FrameTypeUpdate,
    LensTypeCreate,
    LensTypeListResponse,
    LensTypeOut,
    LensTypeUpdate,
    SizeCreate,
    SizeListResponse,
    SizeOut,
    SizeUpdate,
)
from app.schemas import Color, FrameType, LensType, ProductVariant, Size

router = APIRouter(prefix="/admin/opticals", tags=["admin-opticals"], dependencies=[Depends(require_role("admin"))])


def _color_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(ProductVariant.color_id, func.count())
        .where(ProductVariant.color_id.is_not(None))
        .group_by(ProductVariant.color_id)
    ).all()
    return {int(cid): int(n) for cid, n in rows if cid is not None}


def _size_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(ProductVariant.size_id, func.count())
        .where(ProductVariant.size_id.is_not(None))
        .group_by(ProductVariant.size_id)
    ).all()
    return {int(sid): int(n) for sid, n in rows if sid is not None}


# ---- lens types ----

@router.get("/lens-types", response_model=LensTypeListResponse)
def list_lens_types(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> LensTypeListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(LensType)) or 0
    rows = db.scalars(
        select(LensType).order_by(LensType.id.asc()).limit(limit).offset(offset)
    ).all()
    return LensTypeListResponse(
        items=[
            LensTypeOut(
                id=public_id(r.id, "l"),
                name=r.name,
                description=r.description or "",
                price=float(r.price or 0),
                products=0,
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/lens-types", response_model=LensTypeOut, status_code=status.HTTP_201_CREATED)
def create_lens_type(payload: LensTypeCreate, db: Session = Depends(get_db)) -> LensTypeOut:
    if db.scalar(select(LensType).where(LensType.name == payload.name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lens type exists.")
    row = LensType(name=payload.name, description=payload.description, price=payload.price)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return LensTypeOut(
        id=public_id(row.id, "l"),
        name=row.name,
        description=row.description or "",
        price=float(row.price or 0),
        products=0,
    )


@router.patch("/lens-types/{item_id}", response_model=LensTypeOut)
def update_lens_type(
    item_id: int, payload: LensTypeUpdate, db: Session = Depends(get_db)
) -> LensTypeOut:
    row = db.get(LensType, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lens type not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return LensTypeOut(
        id=public_id(row.id, "l"),
        name=row.name,
        description=row.description or "",
        price=float(row.price or 0),
        products=0,
    )


@router.delete("/lens-types/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lens_type(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(LensType, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lens type not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---- frame types ----

@router.get("/frame-types", response_model=FrameTypeListResponse)
def list_frame_types(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> FrameTypeListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(FrameType)) or 0
    rows = db.scalars(
        select(FrameType).order_by(FrameType.id.asc()).limit(limit).offset(offset)
    ).all()
    return FrameTypeListResponse(
        items=[
            FrameTypeOut(
                id=public_id(r.id, "f"),
                name=r.name,
                description=r.description or "",
                products=0,
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/frame-types", response_model=FrameTypeOut, status_code=status.HTTP_201_CREATED)
def create_frame_type(payload: FrameTypeCreate, db: Session = Depends(get_db)) -> FrameTypeOut:
    if db.scalar(select(FrameType).where(FrameType.name == payload.name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Frame type exists.")
    row = FrameType(name=payload.name, description=payload.description)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return FrameTypeOut(
        id=public_id(row.id, "f"),
        name=row.name,
        description=row.description or "",
        products=0,
    )


@router.patch("/frame-types/{item_id}", response_model=FrameTypeOut)
def update_frame_type(
    item_id: int, payload: FrameTypeUpdate, db: Session = Depends(get_db)
) -> FrameTypeOut:
    row = db.get(FrameType, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame type not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return FrameTypeOut(
        id=public_id(row.id, "f"),
        name=row.name,
        description=row.description or "",
        products=0,
    )


@router.delete("/frame-types/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_frame_type(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(FrameType, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame type not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---- colors ----

@router.get("/colors", response_model=ColorListResponse)
def list_colors(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> ColorListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(Color)) or 0
    rows = db.scalars(select(Color).order_by(Color.id.asc()).limit(limit).offset(offset)).all()
    counts = _color_counts(db)
    return ColorListResponse(
        items=[
            ColorOut(
                id=public_id(r.id, "c"),
                name=r.name,
                hex=r.hex,
                products=counts.get(r.id, 0),
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/colors", response_model=ColorOut, status_code=status.HTTP_201_CREATED)
def create_color(payload: ColorCreate, db: Session = Depends(get_db)) -> ColorOut:
    if db.scalar(select(Color).where(Color.name == payload.name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Color exists.")
    row = Color(name=payload.name, hex=payload.hex)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return ColorOut(id=public_id(row.id, "c"), name=row.name, hex=row.hex, products=0)


@router.patch("/colors/{item_id}", response_model=ColorOut)
def update_color(item_id: int, payload: ColorUpdate, db: Session = Depends(get_db)) -> ColorOut:
    row = db.get(Color, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Color not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    counts = _color_counts(db)
    return ColorOut(
        id=public_id(row.id, "c"),
        name=row.name,
        hex=row.hex,
        products=counts.get(row.id, 0),
    )


@router.delete("/colors/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_color(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Color, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Color not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


# ---- sizes ----

@router.get("/sizes", response_model=SizeListResponse)
def list_sizes(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> SizeListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(Size)) or 0
    rows = db.scalars(select(Size).order_by(Size.id.asc()).limit(limit).offset(offset)).all()
    counts = _size_counts(db)
    return SizeListResponse(
        items=[
            SizeOut(
                id=public_id(r.id, "s"),
                name=r.name,
                code=r.code,
                measurement=r.measurement or "",
                products=counts.get(r.id, 0),
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/sizes", response_model=SizeOut, status_code=status.HTTP_201_CREATED)
def create_size(payload: SizeCreate, db: Session = Depends(get_db)) -> SizeOut:
    if db.scalar(select(Size).where((Size.code == payload.code) | (Size.name == payload.name))):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Size exists.")
    row = Size(name=payload.name, code=payload.code, measurement=payload.measurement)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return SizeOut(
        id=public_id(row.id, "s"),
        name=row.name,
        code=row.code,
        measurement=row.measurement or "",
        products=0,
    )


@router.patch("/sizes/{item_id}", response_model=SizeOut)
def update_size(item_id: int, payload: SizeUpdate, db: Session = Depends(get_db)) -> SizeOut:
    row = db.get(Size, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Size not found.")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    counts = _size_counts(db)
    return SizeOut(
        id=public_id(row.id, "s"),
        name=row.name,
        code=row.code,
        measurement=row.measurement or "",
        products=counts.get(row.id, 0),
    )


@router.delete("/sizes/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_size(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Size, item_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Size not found.")
    db.delete(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
