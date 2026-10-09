"""Send every WhatsApp order message for one dummy order to a phone.

Nothing is read from or written to the database.

Usage (from renown-api root, with venv + .env):

    python -m scripts.send_test_order_whatsapp 7845550512
"""

from __future__ import annotations

import sys
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.whatsapp_orders import (
    notify_order_status,
    notify_store_order_status,
    send_order_placed,
)

ORDER_NUMBER = "RO-83291"
PICKUP_ORDER_NUMBER = "RO-83292"
ONLINE_STATUSES = ("verified", "packed", "shipped", "out", "delivered", "cancelled")
PICKUP_STATUSES = ("Preparing", "Ready", "Collected", "Cancelled")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m scripts.send_test_order_whatsapp <10-digit mobile>")
    phone = sys.argv[1]

    customer = SimpleNamespace(name="Reddy", phone=phone)
    order = SimpleNamespace(
        order_number=ORDER_NUMBER,
        total=Decimal("2499.00"),
        payment_method="cod",
        payment_status="pending",
        status="placed",
        courier_name="Delhivery",
        awb_code="1234567890123",
        address=None,
        customer=customer,
    )
    results = [("order_placed", send_order_placed(order, customer))]

    for status in ONLINE_STATUSES:
        time.sleep(1)
        previous, order.status = order.status, status
        results.append((f"order_update: {status}", notify_order_status(order, previous)))

    pickup = SimpleNamespace(
        channel="click_collect",
        order_number=PICKUP_ORDER_NUMBER,
        customer_name="Reddy",
        customer_phone=phone,
        status="Pending",
        store=SimpleNamespace(name="RenOwn EyeWear, Banjara Hills"),
    )
    for status in PICKUP_STATUSES:
        time.sleep(1)
        previous, pickup.status = pickup.status, status
        results.append((f"order_update (pickup): {status}", notify_store_order_status(pickup, previous)))

    for name, ok in results:
        print(f"{'SENT  ' if ok else 'FAILED'} {name}")


if __name__ == "__main__":
    main()
