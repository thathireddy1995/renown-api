"""Seed storefront analytics from 19 Aug through today so the admin UI has a range.

    python -m scripts.seed_web_analytics

Safe to re-run — previous seed rows are tagged in metadata and replaced.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.ist import naive_now
from app.database import SessionLocal
from app.schemas import WebAnalyticsEvent

PATHS = [
    ("/", 38),
    ("/products", 14),
    ("/cart", 12),
    ("/checkout", 8),
    ("/login", 6),
    ("/orders", 5),
    ("/account", 4),
    ("/eye-test", 3),
]
REFERRERS = [(None, 62), ("google.com", 28), ("google.co.in", 6), ("instagram.com", 4)]
COUNTRIES = [("IN", 86), ("US", 6), (None, 4), ("GB", 2), ("AE", 1), ("CA", 1)]
DEVICES = [("mobile", 78), ("desktop", 18), ("tablet", 4)]
DAY_VISITORS = {
    19: 48,
    20: 57,
    21: 41,
    22: 63,
    23: 36,
}


def _pick(rng: random.Random, weighted: list[tuple]) -> object:
    labels, weights = zip(*weighted)
    return rng.choices(list(labels), weights=list(weights), k=1)[0]


def _hash(prefix: str, n: int) -> str:
    return f"{prefix}{n:04d}{n * 17:08x}"[:32]


def main() -> None:
    rng = random.Random(20260819)
    today = naive_now()
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM web_analytics_events WHERE metadata ->> 'seed' = 'true'"))
        rows: list[WebAnalyticsEvent] = []
        visitor_n = 0
        for day in range(19, today.day + 1):
            if day not in DAY_VISITORS:
                continue
            for _ in range(DAY_VISITORS[day]):
                visitor_n += 1
                visitor = _hash("seedv", visitor_n)
                session = _hash("seeds", visitor_n)
                country = _pick(rng, COUNTRIES)
                device = _pick(rng, DEVICES)
                referrer = _pick(rng, REFERRERS)
                bounced = rng.random() < 0.51
                page_count = 1 if bounced else rng.randint(2, 6)
                start = datetime(2026, 8, day, rng.randint(8, 21), rng.randint(0, 59), rng.randint(0, 59))
                if start > today:
                    start = today - timedelta(minutes=rng.randint(8, 90))
                elapsed = 0
                paths: list[str] = []
                for i in range(page_count):
                    path = "/" if i == 0 else str(_pick(rng, PATHS[1:] if page_count > 1 else PATHS))
                    paths.append(path)
                    rows.append(
                        WebAnalyticsEvent(
                            visitor_hash=visitor,
                            session_id=session,
                            event_name="pageview",
                            path=path,
                            referrer=referrer if i == 0 else None,
                            country=country,
                            device=device,
                            metadata_={"seed": True},
                            created_at=start + timedelta(seconds=elapsed),
                        )
                    )
                    elapsed += rng.randint(12, 95)
                if bounced:
                    continue
                if "/cart" in paths or rng.random() < 0.28:
                    rows.append(
                        WebAnalyticsEvent(
                            visitor_hash=visitor,
                            session_id=session,
                            event_name="add_to_cart",
                            path="/cart",
                            referrer=None,
                            country=country,
                            device=device,
                            metadata_={"seed": True},
                            created_at=start + timedelta(seconds=elapsed),
                        )
                    )
                    elapsed += rng.randint(20, 70)
                    if rng.random() < 0.45:
                        rows.append(
                            WebAnalyticsEvent(
                                visitor_hash=visitor,
                                session_id=session,
                                event_name="begin_checkout",
                                path="/checkout",
                                referrer=None,
                                country=country,
                                device=device,
                                metadata_={"seed": True},
                                created_at=start + timedelta(seconds=elapsed),
                            )
                        )
                        elapsed += rng.randint(25, 80)
                        if rng.random() < 0.4:
                            rows.append(
                                WebAnalyticsEvent(
                                    visitor_hash=visitor,
                                    session_id=session,
                                    event_name="purchase",
                                    path="/orders",
                                    referrer=None,
                                    country=country,
                                    device=device,
                                    metadata_={"seed": True},
                                    created_at=start + timedelta(seconds=elapsed),
                                )
                            )
                elif rng.random() < 0.35:
                    rows.append(
                        WebAnalyticsEvent(
                            visitor_hash=visitor,
                            session_id=session,
                            event_name="click",
                            path=paths[-1],
                            referrer=None,
                            country=country,
                            device=device,
                            metadata_={"seed": True, "target": "product"},
                            created_at=start + timedelta(seconds=elapsed),
                        )
                    )
        db.add_all(rows)
        db.commit()
        print(f"seeded {len(rows)} analytics events for {visitor_n} visitors")
    finally:
        db.close()


if __name__ == "__main__":
    main()
