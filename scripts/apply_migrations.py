#!/usr/bin/env python3
"""
Apply SQL migrations from the migrations/ folder to the database.
Migrated files are tracked in a migrations table to prevent re-applying.

Usage:
    python scripts/apply_migrations.py
    python scripts/apply_migrations.py --reset  # Drops migrations table (dev only)
"""

import os
import sys
import glob
from pathlib import Path

import psycopg2
from psycopg2.extensions import connection

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import DATABASE_URL


def get_db_connection() -> connection:
    """Create a PostgreSQL connection from DATABASE_URL."""
    # Parse PostgreSQL connection string
    # Format: postgresql://user:password@host:port/dbname
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def ensure_migrations_table(conn: connection) -> None:
    """Create the migrations tracking table if it doesn't exist."""
    with conn.cursor() as cur:
        # Drop if exists to ensure clean state
        cur.execute("DROP TABLE IF EXISTS schema_migrations;")
        cur.execute(
            """
            CREATE TABLE schema_migrations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()


def get_applied_migrations(conn: connection) -> set[str]:
    """Get the set of already-applied migration names."""
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations ORDER BY name;")
        return {row[0] for row in cur.fetchall()}


def apply_migration(conn: connection, migration_name: str, sql_content: str) -> bool:
    """Apply a single migration and track it."""
    try:
        with conn.cursor() as cur:
            # Execute the SQL
            cur.execute(sql_content)
            # Track that we applied it
            cur.execute(
                "INSERT INTO schema_migrations (name) VALUES (%s);",
                (migration_name,),
            )
            conn.commit()
        print(f"✅ Applied: {migration_name}")
        return True
    except psycopg2.Error as e:
        conn.rollback()
        print(f"❌ Failed: {migration_name}")
        print(f"   Error: {e}")
        return False


def list_migration_files() -> list[tuple[str, str]]:
    """List all SQL migration files in migrations/ folder, sorted by name."""
    migrations_dir = Path(__file__).parent.parent / "migrations"
    sql_files = sorted(migrations_dir.glob("*.sql"))
    return [(f.name, f.read_text()) for f in sql_files]


def main() -> None:
    """Main entry point."""
    args = sys.argv[1:]
    reset_mode = "--reset" in args

    print("Connecting to database...")
    try:
        conn = get_db_connection()
    except psycopg2.Error as e:
        print(f"❌ Failed to connect: {e}")
        sys.exit(1)

    print("Ensuring migrations table exists...")
    ensure_migrations_table(conn)

    if reset_mode:
        print("\n⚠️  --reset mode: Dropping migrations table (dev only)...")
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS schema_migrations;")
            conn.commit()
        ensure_migrations_table(conn)
        print("   Migrations table reset.")

    print("\nFetching applied migrations...")
    applied = get_applied_migrations(conn)
    print(f"   Found {len(applied)} applied migration(s)")

    print("\nFetching pending migrations...")
    all_migrations = list_migration_files()
    pending = [
        (name, sql) for name, sql in all_migrations if name not in applied
    ]
    print(f"   Found {len(pending)} pending migration(s)")

    if not pending:
        print("\n✨ All migrations already applied!")
        conn.close()
        return

    print("\nApplying pending migrations...")
    failed = False
    for name, sql in pending:
        if not apply_migration(conn, name, sql):
            failed = True

    if failed:
        print("\n❌ Some migrations failed. Check the errors above.")
        conn.close()
        sys.exit(1)
    else:
        print("\n✅ All migrations applied successfully!")
        conn.close()


if __name__ == "__main__":
    main()
