"""Admin operations — export, bulk upload, import job history."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.catalog_lookups import brand_id_for, category_id_for
from app.core.catalog_serialize import slugify
from app.core.deps import TokenPrincipal, require_role
from app.database import get_db
from app.deps import pagination
from app.dto.operations_dto import (
    BulkUploadPreviewRow,
    BulkUploadRequest,
    BulkUploadResponse,
    BulkUploadValidateResponse,
    ImportJobListResponse,
    ImportJobOut,
)
from app.schemas import (
    Brand,
    Category,
    Customer,
    ImportJob,
    Order,
    Product,
    ProductVariant,
    User,
    WarehouseInventory,
)

router = APIRouter(
    prefix="/admin/operations",
    tags=["admin-operations"],
    dependencies=[Depends(require_role("admin"))],
)

STATUS_UI = {
    "pending": "Pending",
    "processing": "Processing",
    "completed": "Completed",
    "failed": "Failed",
}

MAX_BULK_ROWS = 500


def _job_out(row: ImportJob) -> ImportJobOut:
    return ImportJobOut(
        id=f"im-{row.id}",
        file=row.file_name,
        rows=row.row_count,
        status=STATUS_UI.get(row.status, row.status.title()),
        by=row.created_by or "Admin",
        date=(row.created_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M"),
    )


def _validate_rows(rows: list) -> tuple[list[BulkUploadPreviewRow], list]:
    preview: list[BulkUploadPreviewRow] = []
    valid_payloads = []
    for i, r in enumerate(rows, start=1):
        name = (r.name or "").strip()
        sku = (r.sku or "").strip()
        error = None
        if not sku:
            error = "Missing SKU"
        elif not name:
            error = "Missing product name"
        preview.append(
            BulkUploadPreviewRow(
                row=i,
                name=name,
                brand=(r.brand or "").strip(),
                sku=sku,
                price=float(r.price or 0),
                stock=int(r.stock or 0),
                valid=error is None,
                error=error,
            )
        )
        if error is None:
            valid_payloads.append(r)
    return preview, valid_payloads


@router.get("/import-jobs", response_model=ImportJobListResponse)
def list_import_jobs(
    db: Session = Depends(get_db),
    page: tuple[int, int] = Depends(pagination),
) -> ImportJobListResponse:
    limit, offset = page
    total = db.scalar(select(func.count()).select_from(ImportJob)) or 0
    rows = db.scalars(
        select(ImportJob)
        .order_by(ImportJob.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ImportJobListResponse(
        items=[_job_out(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/bulk-upload/validate", response_model=BulkUploadValidateResponse)
def validate_bulk_upload(body: BulkUploadRequest) -> BulkUploadValidateResponse:
    rows = body.rows[:MAX_BULK_ROWS]
    preview, valid = _validate_rows(rows)
    return BulkUploadValidateResponse(
        total=len(preview),
        valid=len(valid),
        errors=len(preview) - len(valid),
        preview=preview,
    )


@router.post("/bulk-upload", response_model=BulkUploadResponse)
def bulk_upload(
    body: BulkUploadRequest,
    db: Session = Depends(get_db),
    principal: TokenPrincipal = Depends(require_role("admin")),
) -> BulkUploadResponse:
    rows = body.rows[:MAX_BULK_ROWS]
    preview, valid_rows = _validate_rows(rows)
    error_count = len(preview) - len(valid_rows)

    creator = body.created_by
    if not creator:
        user = db.get(User, principal.sub)
        creator = user.name if user else "Admin"

    job = ImportJob(
        job_type="products",
        file_name=body.file_name or "upload.csv",
        status="processing",
        row_count=0,
        error_count=error_count,
        created_by=creator,
    )
    db.add(job)
    db.flush()

    if not valid_rows:
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return BulkUploadResponse(
            job_id=f"im-{job.id}",
            imported=0,
            errors=error_count,
            status="Failed",
        )

    # Resolve brands/categories once (batch), then bulk upsert
    brand_names = { (r.brand or "").strip() for r in valid_rows if (r.brand or "").strip() }
    cat_names = { (r.category or "").strip() for r in valid_rows if (r.category or "").strip() }
    brand_map = {n: brand_id_for(db, n) for n in brand_names}
    cat_map = {n: category_id_for(db, n) for n in cat_names}

    # Ensure missing brands/categories exist via bulk insert
    for n in brand_names:
        if brand_map[n] is None:
            db.add(Brand(name=n, slug=slugify(n)[:140], status="active"))
    for n in cat_names:
        if cat_map[n] is None:
            db.add(Category(name=n, slug=slugify(n)[:140], status="active"))
    if brand_names or cat_names:
        db.flush()
        brand_map = {n: brand_id_for(db, n) for n in brand_names}
        cat_map = {n: category_id_for(db, n) for n in cat_names}

    product_rows = []
    seen_skus: set[str] = set()
    for r in valid_rows:
        sku = r.sku.strip()
        if sku in seen_skus:
            error_count += 1
            continue
        seen_skus.add(sku)
        name = r.name.strip()
        product_rows.append(
            {
                "name": name,
                "slug": slugify(name)[:220] or slugify(sku)[:220],
                "sku": sku,
                "price": Decimal(str(r.price or 0)),
                "brand_id": brand_map.get((r.brand or "").strip()),
                "category_id": cat_map.get((r.category or "").strip()),
                "status": "active",
            }
        )

    if product_rows:
        stmt = pg_insert(Product).values(product_rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Product.sku],
            set_={
                "name": stmt.excluded.name,
                "price": stmt.excluded.price,
                "brand_id": stmt.excluded.brand_id,
                "category_id": stmt.excluded.category_id,
                "status": "active",
            },
        )
        db.execute(stmt)
        db.flush()

        # Map sku → product_id for variants
        skus = [p["sku"] for p in product_rows]
        products = db.scalars(select(Product).where(Product.sku.in_(skus))).all()
        by_sku = {p.sku: p for p in products}

        variant_rows = []
        for r in valid_rows:
            sku = r.sku.strip()
            p = by_sku.get(sku)
            if not p:
                continue
            variant_rows.append(
                {
                    "product_id": p.id,
                    "sku": sku,
                    "color": (r.color or "").strip() or None,
                    "size": (r.size or "").strip() or None,
                    "price": Decimal(str(r.price or 0)),
                    "stock": int(r.stock or 0),
                }
            )
        if variant_rows:
            vstmt = pg_insert(ProductVariant).values(variant_rows)
            vstmt = vstmt.on_conflict_do_update(
                index_elements=[ProductVariant.sku],
                set_={
                    "price": vstmt.excluded.price,
                    "stock": vstmt.excluded.stock,
                    "color": vstmt.excluded.color,
                    "size": vstmt.excluded.size,
                },
            )
            db.execute(vstmt)

    imported = len(product_rows)
    job.row_count = imported
    job.error_count = error_count
    job.status = "completed" if imported else "failed"
    job.completed_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return BulkUploadResponse(
        job_id=f"im-{job.id}",
        imported=imported,
        errors=error_count,
        status=STATUS_UI[job.status],
    )


def _csv_stream(headers: list[str], row_iter):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)
    for row in row_iter:
        writer.writerow(row)
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)


@router.post("/export/{entity}")
def export_entity(
    entity: str,
    db: Session = Depends(get_db),
):
    key = entity.strip().lower()
    if key not in {"products", "orders", "customers", "inventory"}:
        raise HTTPException(status_code=400, detail="Unsupported export entity")

    if key == "products":
        headers = ["id", "sku", "name", "price", "status", "stock"]
        result = db.execute(
            select(
                Product.id,
                Product.sku,
                Product.name,
                Product.price,
                Product.status,
                func.coalesce(func.sum(ProductVariant.stock), 0),
            )
            .outerjoin(ProductVariant, ProductVariant.product_id == Product.id)
            .group_by(Product.id)
            .order_by(Product.id.asc())
            .execution_options(yield_per=200)
        )

        def rows():
            for r in result:
                yield [r[0], r[1], r[2], float(r[3] or 0), r[4], int(r[5] or 0)]

    elif key == "orders":
        headers = ["order_number", "customer_id", "status", "total", "created_at"]
        result = db.execute(
            select(
                Order.order_number,
                Order.customer_id,
                Order.status,
                Order.total,
                Order.created_at,
            )
            .order_by(Order.id.asc())
            .execution_options(yield_per=200)
        )

        def rows():
            for r in result:
                yield [
                    r[0],
                    r[1],
                    r[2],
                    float(r[3] or 0),
                    r[4].isoformat() if r[4] else "",
                ]

    elif key == "customers":
        headers = ["id", "name", "phone", "email", "is_active", "created_at"]
        result = db.execute(
            select(
                Customer.id,
                Customer.name,
                Customer.phone,
                Customer.email,
                Customer.is_active,
                Customer.created_at,
            )
            .order_by(Customer.id.asc())
            .execution_options(yield_per=200)
        )

        def rows():
            for r in result:
                yield [
                    r[0],
                    r[1] or "",
                    r[2],
                    r[3] or "",
                    r[4],
                    r[5].isoformat() if r[5] else "",
                ]

    else:  # inventory
        headers = ["variant_id", "warehouse_id", "on_hand", "reserved", "reorder_point"]
        result = db.execute(
            select(
                WarehouseInventory.variant_id,
                WarehouseInventory.warehouse_id,
                WarehouseInventory.on_hand,
                WarehouseInventory.reserved,
                WarehouseInventory.reorder_point,
            )
            .order_by(WarehouseInventory.id.asc())
            .execution_options(yield_per=200)
        )

        def rows():
            for r in result:
                yield list(r)

    filename = f"{key}-export.csv"
    return StreamingResponse(
        _csv_stream(headers, rows()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
