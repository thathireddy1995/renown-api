CREATE TABLE IF NOT EXISTS pick_lists (
    id BIGSERIAL PRIMARY KEY,
    list_number VARCHAR(40) NOT NULL,
    wave_number VARCHAR(80) NOT NULL,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses (id) ON DELETE RESTRICT,
    picker_name VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pick_lists_list_number ON pick_lists (list_number);
CREATE INDEX IF NOT EXISTS ix_pick_lists_warehouse_id ON pick_lists (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_pick_lists_status ON pick_lists (status);

CREATE TABLE IF NOT EXISTS pick_list_items (
    id BIGSERIAL PRIMARY KEY,
    pick_list_id BIGINT NOT NULL REFERENCES pick_lists (id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE RESTRICT,
    qty INT NOT NULL DEFAULT 0,
    picked_qty INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_pick_list_items_pick_list_id ON pick_list_items (pick_list_id);
CREATE INDEX IF NOT EXISTS ix_pick_list_items_variant_id ON pick_list_items (variant_id);

CREATE TABLE IF NOT EXISTS dispatch_orders (
    id BIGSERIAL PRIMARY KEY,
    do_number VARCHAR(40) NOT NULL,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses (id) ON DELETE RESTRICT,
    destination_type VARCHAR(20) NOT NULL,
    destination_id BIGINT,
    destination_label VARCHAR(200),
    carrier VARCHAR(80),
    awb VARCHAR(80),
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_dispatch_orders_do_number ON dispatch_orders (do_number);
CREATE INDEX IF NOT EXISTS ix_dispatch_orders_warehouse_id ON dispatch_orders (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_dispatch_orders_status ON dispatch_orders (status);
CREATE INDEX IF NOT EXISTS ix_dispatch_orders_destination_id ON dispatch_orders (destination_id);

CREATE TABLE IF NOT EXISTS dispatch_order_items (
    id BIGSERIAL PRIMARY KEY,
    dispatch_order_id BIGINT NOT NULL REFERENCES dispatch_orders (id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE RESTRICT,
    qty INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_dispatch_order_items_dispatch_order_id
    ON dispatch_order_items (dispatch_order_id);
CREATE INDEX IF NOT EXISTS ix_dispatch_order_items_variant_id
    ON dispatch_order_items (variant_id);

CREATE TABLE IF NOT EXISTS packs (
    id BIGSERIAL PRIMARY KEY,
    pack_number VARCHAR(40) NOT NULL,
    dispatch_order_id BIGINT REFERENCES dispatch_orders (id) ON DELETE SET NULL,
    packer_name VARCHAR(120),
    boxes INT NOT NULL DEFAULT 0,
    weight NUMERIC(10, 2),
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_packs_pack_number ON packs (pack_number);
CREATE INDEX IF NOT EXISTS ix_packs_dispatch_order_id ON packs (dispatch_order_id);
CREATE INDEX IF NOT EXISTS ix_packs_status ON packs (status);
