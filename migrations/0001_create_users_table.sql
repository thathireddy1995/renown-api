-- Users table for admin, store_manager, and warehouse_manager portal logins.

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(160) NOT NULL,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_role_check CHECK (role IN ('admin', 'store_manager', 'warehouse_manager'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (email);
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_phone ON users (phone) WHERE phone IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_users_role ON users (role);
CREATE INDEX IF NOT EXISTS ix_users_role_active ON users (role, is_active);
