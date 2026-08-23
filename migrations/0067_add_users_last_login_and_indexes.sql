-- Login activity + Lambda-friendly lookup indexes on the existing users table.
-- Do not create a second users table — this is the staff/admin login source of truth.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_login TIMESTAMP NULL;

CREATE INDEX IF NOT EXISTS ix_users_is_active ON users (is_active);
CREATE INDEX IF NOT EXISTS ix_users_last_login ON users (last_login DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_users_name_lower ON users (lower(name));
CREATE INDEX IF NOT EXISTS ix_users_role_store ON users (role, store_id);
CREATE INDEX IF NOT EXISTS ix_users_role_warehouse ON users (role, warehouse_id);

-- Prefix / ILIKE search on name + phone (RDS PostgreSQL ships pg_trgm).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS ix_users_name_trgm ON users USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_users_phone_trgm ON users USING gin (phone gin_trgm_ops);
