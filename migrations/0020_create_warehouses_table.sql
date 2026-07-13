CREATE TABLE IF NOT EXISTS warehouses (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    city VARCHAR(80),
    country VARCHAR(80),
    manager VARCHAR(120),
    capacity INT NOT NULL DEFAULT 0,
    staff INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_warehouses_code ON warehouses (code);
CREATE INDEX IF NOT EXISTS ix_warehouses_status ON warehouses (status);
