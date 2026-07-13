CREATE TABLE IF NOT EXISTS transfer_requests (
    id BIGSERIAL PRIMARY KEY,
    request_number VARCHAR(40) NOT NULL,
    store_id BIGINT REFERENCES stores (id) ON DELETE RESTRICT,
    requester_warehouse_id BIGINT REFERENCES warehouses (id) ON DELETE RESTRICT,
    target_warehouse_id BIGINT REFERENCES warehouses (id) ON DELETE RESTRICT,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE RESTRICT,
    qty_requested INT NOT NULL DEFAULT 0,
    urgency VARCHAR(20) NOT NULL DEFAULT 'Medium',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    stock_transfer_id BIGINT REFERENCES stock_transfers (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_transfer_requests_request_number
    ON transfer_requests (request_number);
CREATE INDEX IF NOT EXISTS ix_transfer_requests_store_id ON transfer_requests (store_id);
CREATE INDEX IF NOT EXISTS ix_transfer_requests_status ON transfer_requests (status);
CREATE INDEX IF NOT EXISTS ix_transfer_requests_requester_warehouse_id
    ON transfer_requests (requester_warehouse_id);
CREATE INDEX IF NOT EXISTS ix_transfer_requests_target_warehouse_id
    ON transfer_requests (target_warehouse_id);
CREATE INDEX IF NOT EXISTS ix_transfer_requests_variant_id
    ON transfer_requests (variant_id);
