"""Apply every migrations/*.sql file against DATABASE_URL, in order, exactly once.

Tracks applied files in a schema_migrations table so re-runs are idempotent
even though most individual migration files also use IF NOT EXISTS. This is
the only supported way to apply schema changes outside of writing the .sql
file itself (see api_rules.txt §2) — never run ad-hoc DDL elsewhere.

Usage:
    source venv/bin/activate
    python -m scripts.run_migrations                    # Apply all pending migrations
    python -m scripts.run_migrations 45                 # Apply migrations 0045 and above
    python -m scripts.run_migrations --from 45          # Same as above
    python -m scripts.run_migrations --from 45 --to 50  # Apply migrations 0045-0050
"""

import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parent.parent))

import psycopg2

from app.core.config import DATABASE_URL

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"


def _psycopg2_dsn(url: str) -> str:
    """Convert SQLAlchemy URLs (postgresql+psycopg://…) to a psycopg2 DSN."""
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres+psycopg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def parse_args() -> tuple[int | None, int | None]:
    """Parse CLI arguments: --from 45 --to 50, or just 45."""
    from_num = None
    to_num = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--from", "-f"):
            if i + 1 < len(args):
                try:
                    from_num = int(args[i + 1])
                    i += 2
                    continue
                except ValueError:
                    pass
        elif arg in ("--to", "-t"):
            if i + 1 < len(args):
                try:
                    to_num = int(args[i + 1])
                    i += 2
                    continue
                except ValueError:
                    pass
        elif arg.isdigit():
            # Shorthand: just a number means --from that number
            from_num = int(arg)
            i += 1
            continue

        print(f"Unknown argument: {arg}")
        sys.exit(1)

    return from_num, to_num


def filter_migrations(
    files: list[pathlib.Path], from_num: int | None, to_num: int | None
) -> list[pathlib.Path]:
    """Filter migration files based on --from and --to numbers."""
    if from_num is None and to_num is None:
        return files

    filtered = []
    for f in files:
        # Extract number from filename like "0045_description.sql"
        try:
            num = int(f.name.split("_")[0])
        except (ValueError, IndexError):
            continue

        if from_num is not None and num < from_num:
            continue
        if to_num is not None and num > to_num:
            continue

        filtered.append(f)

    return filtered


def main() -> None:
    from_num, to_num = parse_args()

    if from_num is not None or to_num is not None:
        from_str = f"from {from_num}" if from_num is not None else ""
        to_str = f"to {to_num}" if to_num is not None else ""
        range_str = f" ({from_str} {to_str})".strip()
        print(f"Running migrations{range_str}...")
    else:
        print("Running all pending migrations...")

    conn = psycopg2.connect(_psycopg2_dsn(DATABASE_URL))
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # Handle both old (filename) and new (name) column names
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

            # Try to query with 'name' column (new schema), fallback to 'filename' (old)
            try:
                cur.execute("SELECT name FROM schema_migrations")
                already_applied = {row[0] for row in cur.fetchall()}
            except psycopg2.Error:
                conn.rollback()
                try:
                    cur.execute("SELECT filename FROM schema_migrations")
                    already_applied = {row[0] for row in cur.fetchall()}
                except psycopg2.Error:
                    already_applied = set()

        files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: p.name)
        files = filter_migrations(files, from_num, to_num)

        applied_now = []
        for f in files:
            if f.name in already_applied:
                print(f"⏭️  skipped (already applied): {f.name}")
                continue
            sql = f.read_text()
            with conn.cursor() as cur:
                cur.execute(sql)
                try:
                    cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
                except psycopg2.Error:
                    conn.rollback()
                    try:
                        cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,))
                    except psycopg2.Error:
                        pass  # Table might not exist yet or have different schema
            conn.commit()
            applied_now.append(f.name)
            print(f"✅ applied: {f.name}")

        if not applied_now:
            print("\n✨ no pending migrations — database is up to date")
        else:
            print(f"\n✅ {len(applied_now)} migration(s) applied successfully!")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
