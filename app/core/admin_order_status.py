"""Shared admin status display labels (avoid circular router imports)."""

STATUS_LABEL = {
    "placed": "Processing",
    "verified": "Processing",
    "packed": "Processing",
    "shipped": "Shipped",
    "out": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def admin_status_label(raw: str) -> str:
    return STATUS_LABEL.get((raw or "").lower(), (raw or "Processing").title())
