"""Per-category GST rate / HSN with company-wide fallback.

Callers must eager-load ``Product.category`` — these helpers never query.
"""

from __future__ import annotations

from decimal import Decimal

from app.schemas import Category

DEFAULT_HSN = "90049090"


def category_gst_percent(category: Category | None) -> float | None:
    """Category override, or None so the client falls back to the company GST %."""
    if category is None or category.gst_percent is None:
        return None
    return float(category.gst_percent)


def category_hsn(category: Category | None) -> str | None:
    code = (category.hsn_code or "").strip() if category is not None else ""
    return code or None


def effective_gst_percent(category: Category | None, company_percent: Decimal) -> Decimal:
    if category is None or category.gst_percent is None:
        return company_percent
    return Decimal(str(category.gst_percent))


def effective_hsn(category: Category | None) -> str:
    return category_hsn(category) or DEFAULT_HSN
