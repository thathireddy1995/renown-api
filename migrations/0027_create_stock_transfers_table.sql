CREATE TABLE IF NOT EXISTS stock_transfers (
    id BIGSERIAL PRIMARY KEY,
    transfer_number VARCHAR(40) NOT NULL,
    from_warehouse_id BIGINT NOT NULL REFERENCES warehouses (id) ON DELETE RESTRICT,
    to_warehouse_id BIGINT REFERENCES warehouses (id) ON DELETE RESTRICT,
    to_store_id BIGINT REFERENCES stores (id) ON DELETE RESTRICT,
    status VARCHAR(30) NOT NULL DEFAULT 'requested',
    requested_by VARCHAR(120),
    eta DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_transfers_transfer_number
    ON stock_transfers (transfer_number);
CREATE INDEX IF NOT EXISTS ix_stock_transfers_status ON stock_transfers (status);
CREATE INDEX IF NOT EXISTS ix_stock_transfers_from_warehouse_id
    ON stock_transfers (from_warehouse_id);
CREATE INDEX IF NOT EXISTS ix_stock_transfers_to_warehouse_id
    ON stock_transfers (to_warehouse_id);
CREATE INDEX IF NOT EXISTS ix_stock_transfers_to_store_id
    ON stock_transfers (to_store_id);

CREATE TABLE IF NOT EXISTS stock_transfer_items (
    id BIGSERIAL PRIMARY KEY,
    stock_transfer_id BIGINT NOT NULL REFERENCES stock_transfers (id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE RESTRICT,
    qty INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_stock_transfer_items_stock_transfer_id
    ON stock_transfer_items (stock_transfer_id);
CREATE INDEX IF NOT EXISTS ix_stock_transfer_items_variant_id
    ON stock_transfer_items (variant_id);
