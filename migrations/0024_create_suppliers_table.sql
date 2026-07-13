CREATE TABLE IF NOT EXISTS suppliers (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(40) NOT NULL,
    name VARCHAR(160) NOT NULL,
    contact VARCHAR(160),
    category VARCHAR(120),
    lead_time_days INT NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_suppliers_code ON suppliers (code);
CREATE INDEX IF NOT EXISTS ix_suppliers_status ON suppliers (status);
