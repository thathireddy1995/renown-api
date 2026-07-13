"""Shared helpers for taxonomy / optical admin serializers."""

from datetime import datetime

from app.core.catalog_serialize import slugify


def status_label(status: str | None) -> str:
    raw = (status or "active").lower()
    return "Active" if raw == "active" else "Draft"


def status_store(value: str | None) -> str:
    if not value:
        return "active"
    v = value.strip().lower()
    if v in ("active", "draft"):
        return v
    if v == "active":
        return "active"
    return "draft" if "draft" in v else "active"


def type_label(attr_type: str | None) -> str:
    raw = (attr_type or "select").lower()
    return "Boolean" if raw == "boolean" else "Select"


def type_store(value: str | None) -> str:
    if not value:
        return "select"
    v = value.strip().lower()
    return "boolean" if "bool" in v else "select"


def format_updated(dt: datetime | None) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d")


def public_id(row_id: int, prefix: str = "") -> str:
    if prefix:
        return f"{prefix}{row_id}"
    return str(row_id).zfill(4)


def ensure_slug(name: str, slug: str | None) -> str:
    return slug.strip() if slug and slug.strip() else slugify(name)
