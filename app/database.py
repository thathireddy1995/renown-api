from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATABASE_URL

# Created once at module import time. A warm Lambda container re-imports
# nothing on subsequent invocations, so this engine/pool is reused across
# requests instead of reconnecting every time (see api_rules.txt §5, §6).
#
# pool_size is kept small because each Lambda container handles one request
# at a time — a large pool here just holds idle connections open on Neon.
# pool_pre_ping detects connections that Neon or a frozen/thawed Lambda
# container has silently dropped, and transparently reconnects before reuse.
# pool_recycle proactively refreshes connections before Neon's own idle
# timeout can kill them mid-request.
engine = create_engine(
    DATABASE_URL,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_timeout=10,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency. Routers must use this — never open a raw
    connection or create a new engine inline (api_rules.txt §6)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
