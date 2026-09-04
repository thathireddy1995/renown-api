from collections.abc import Generator
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import certifi
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import DATABASE_URL

# DATABASE_URL comes from renown-api/.env (local) or Lambda env (prod).
# Current target: db.renowneyewear.com:6432 / renown_db via PgBouncer + TLS.
# Old IP URL (commented in .env):
#   ...@103.86.177.116:6432/renown_db?sslmode=verify-full&sslrootcert=...
#
# verify-full without sslrootcert uses certifi's CA bundle so local macOS and
# Lambda both trust Let's Encrypt (including newer LE intermediates).


def _database_url() -> str:
    parsed = urlparse(DATABASE_URL)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.get("sslmode") in {"verify-full", "verify-ca"} and "sslrootcert" not in query:
        query["sslrootcert"] = certifi.where()
        return urlunparse(parsed._replace(query=urlencode(query)))
    return DATABASE_URL


# Created once at module import time. A warm Lambda container re-imports
# nothing on subsequent invocations, so this engine/pool is reused across
# requests instead of reconnecting every time (see api_rules.txt §5, §6).
#
# pool_size is kept small because each Lambda container handles one request
# at a time — a large pool here just holds idle connections open on the DB.
# pool_pre_ping detects connections that PgBouncer or a frozen/thawed Lambda
# container has silently dropped, and transparently reconnects before reuse.
# pool_recycle proactively refreshes connections before idle timeouts can
# kill them mid-request.
engine = create_engine(
    _database_url(),
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=280,
    connect_args={"options": "-c timezone=Asia/Kolkata"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _set_ist_timezone(dbapi_connection, *_args) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("SET TIME ZONE 'Asia/Kolkata'")
    cursor.close()


event.listen(engine, "connect", _set_ist_timezone)
event.listen(engine, "checkout", _set_ist_timezone)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency. Routers must use this — never open a raw
    connection or create a new engine inline (api_rules.txt §6)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
