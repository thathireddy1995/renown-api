CREATE TABLE IF NOT EXISTS store_inventory (
    id BIGSERIAL PRIMARY KEY,
    store_id BIGINT NOT NULL REFERENCES stores (id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE CASCADE,
    on_hand INT NOT NULL DEFAULT 0,
    on_floor INT NOT NULL DEFAULT 0,
    backroom INT NOT NULL DEFAULT 0,
    reserved INT NOT NULL DEFAULT 0,
    reorder_point INT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (store_id, variant_id)
);

CREATE INDEX IF NOT EXISTS ix_store_inventory_variant_id
    ON store_inventory (variant_id);
CREATE INDEX IF NOT EXISTS ix_store_inventory_store_id
    ON store_inventory (store_id);
