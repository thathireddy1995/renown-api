"""Apply every migrations/*.sql file against DATABASE_URL, in order, exactly once.

Tracks applied files in a schema_migrations table so re-runs are idempotent
even though most individual migration files also use IF NOT EXISTS. This is
the only supported way to apply schema changes outside of writing the .sql
file itself (see api_rules.txt §2) — never run ad-hoc DDL elsewhere.

Usage:
    source venv/bin/activate
    python -m scripts.run_migrations
"""

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

import psycopg2

from app.core.config import DATABASE_URL

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.commit()

            cur.execute("SELECT filename FROM schema_migrations")
            already_applied = {row[0] for row in cur.fetchall()}

        files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
        applied_now = []
        for f in files:
            if f.name in already_applied:
                continue
            sql = f.read_text()
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,)
                )
            conn.commit()
            applied_now.append(f.name)
            print(f"applied: {f.name}")

        if not applied_now:
            print("no pending migrations — database is up to date")
        else:
            print(f"\n{len(applied_now)} migration(s) applied.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
