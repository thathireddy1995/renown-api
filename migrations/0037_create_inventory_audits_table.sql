CREATE TABLE IF NOT EXISTS inventory_audits (
    id BIGSERIAL PRIMARY KEY,
    audit_number VARCHAR(40) NOT NULL,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses(id) ON DELETE RESTRICT,
    zone VARCHAR(80),
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    auditor_name VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT inventory_audits_status_check CHECK (
        status IN ('scheduled', 'in_progress', 'completed')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_audits_audit_number
    ON inventory_audits (audit_number);
CREATE INDEX IF NOT EXISTS ix_inventory_audits_warehouse_id
    ON inventory_audits (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_inventory_audits_status
    ON inventory_audits (status);

CREATE TABLE IF NOT EXISTS inventory_audit_items (
    id BIGSERIAL PRIMARY KEY,
    inventory_audit_id BIGINT NOT NULL REFERENCES inventory_audits(id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
    expected_qty INT NOT NULL DEFAULT 0,
    counted_qty INT NOT NULL DEFAULT 0,
    variance INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_inventory_audit_items_inventory_audit_id
    ON inventory_audit_items (inventory_audit_id);
CREATE INDEX IF NOT EXISTS ix_inventory_audit_items_variant_id
    ON inventory_audit_items (variant_id);
