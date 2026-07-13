CREATE TABLE IF NOT EXISTS purchase_orders (
    id BIGSERIAL PRIMARY KEY,
    po_number VARCHAR(40) NOT NULL,
    supplier_id BIGINT NOT NULL REFERENCES suppliers (id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'Open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_purchase_orders_po_number ON purchase_orders (po_number);
CREATE INDEX IF NOT EXISTS ix_purchase_orders_supplier_id ON purchase_orders (supplier_id);
CREATE INDEX IF NOT EXISTS ix_purchase_orders_status ON purchase_orders (status);

CREATE TABLE IF NOT EXISTS grn (
    id BIGSERIAL PRIMARY KEY,
    grn_number VARCHAR(40) NOT NULL,
    purchase_order_id BIGINT NOT NULL REFERENCES purchase_orders (id) ON DELETE RESTRICT,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses (id) ON DELETE RESTRICT,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending',
    received_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_grn_grn_number ON grn (grn_number);
CREATE INDEX IF NOT EXISTS ix_grn_purchase_order_id ON grn (purchase_order_id);
CREATE INDEX IF NOT EXISTS ix_grn_warehouse_id ON grn (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_grn_status ON grn (status);

CREATE TABLE IF NOT EXISTS grn_items (
    id BIGSERIAL PRIMARY KEY,
    grn_id BIGINT NOT NULL REFERENCES grn (id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE RESTRICT,
    qty_ordered INT NOT NULL DEFAULT 0,
    qty_received INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_grn_items_grn_id ON grn_items (grn_id);
CREATE INDEX IF NOT EXISTS ix_grn_items_variant_id ON grn_items (variant_id);
