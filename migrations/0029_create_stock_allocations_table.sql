CREATE TABLE IF NOT EXISTS stock_allocations (
    id BIGSERIAL PRIMARY KEY,
    allocation_number VARCHAR(40) NOT NULL,
    order_id BIGINT REFERENCES orders (id) ON DELETE SET NULL,
    order_number VARCHAR(40),
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE RESTRICT,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses (id) ON DELETE RESTRICT,
    qty INT NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    picker_name VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_stock_allocations_allocation_number
    ON stock_allocations (allocation_number);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_order_id ON stock_allocations (order_id);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_status ON stock_allocations (status);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_variant_id ON stock_allocations (variant_id);
CREATE INDEX IF NOT EXISTS ix_stock_allocations_warehouse_id
    ON stock_allocations (warehouse_id);
