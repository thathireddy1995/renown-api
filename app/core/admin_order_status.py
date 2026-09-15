"""Shared admin status display labels (avoid circular router imports)."""

STATUS_LABEL = {
    "placed": "Processing",
    "verified": "Processing",
    "packed": "Processing",
    "partner_assigned": "Partner Assigned",
    "shipped": "Shipped",
    "out": "Shipped",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}

# Customer track-order ladder (warehouse Online deliveries UI).
TRACK_STATUS_LABEL = {
    "placed": "Order Placed",
    "verified": "Prescription Verified",
    "packed": "Packed",
    "partner_assigned": "Delivery Partner Assigned",
    "shipped": "Shipped",
    "out": "Out for Delivery",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}


def admin_status_label(raw: str) -> str:
    return STATUS_LABEL.get((raw or "").lower(), (raw or "Processing").title())


def track_status_label(raw: str) -> str:
    return TRACK_STATUS_LABEL.get((raw or "").lower(), (raw or "Order Placed").title())
