CREATE TABLE IF NOT EXISTS stores (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    address VARCHAR(200),
    city VARCHAR(80),
    country VARCHAR(80),
    phone VARCHAR(40),
    hours VARCHAR(80),
    manager VARCHAR(120),
    staff INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'Open',
    today_revenue NUMERIC(12, 2) NOT NULL DEFAULT 0,
    today_orders INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_stores_code ON stores (code);
CREATE INDEX IF NOT EXISTS ix_stores_status ON stores (status);
