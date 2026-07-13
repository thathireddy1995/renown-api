CREATE TABLE IF NOT EXISTS warehouse_inventory (
    id BIGSERIAL PRIMARY KEY,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses (id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE CASCADE,
    bin_location VARCHAR(40),
    on_hand INT NOT NULL DEFAULT 0,
    reserved INT NOT NULL DEFAULT 0,
    reorder_point INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (warehouse_id, variant_id)
);

CREATE INDEX IF NOT EXISTS ix_warehouse_inventory_variant_id
    ON warehouse_inventory (variant_id);
CREATE INDEX IF NOT EXISTS ix_warehouse_inventory_warehouse_id
    ON warehouse_inventory (warehouse_id);
