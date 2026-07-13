CREATE TABLE IF NOT EXISTS store_orders (
    id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL,
    store_id BIGINT NOT NULL REFERENCES stores (id) ON DELETE RESTRICT,
    customer_name VARCHAR(160),
    channel VARCHAR(30) NOT NULL DEFAULT 'in_store',
    payment_method VARCHAR(20) NOT NULL DEFAULT 'cash',
    associate_name VARCHAR(120),
    subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total NUMERIC(12, 2) NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'Completed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_store_orders_order_number
    ON store_orders (order_number);
CREATE INDEX IF NOT EXISTS ix_store_orders_store_id ON store_orders (store_id);
CREATE INDEX IF NOT EXISTS ix_store_orders_status ON store_orders (status);
CREATE INDEX IF NOT EXISTS ix_store_orders_channel ON store_orders (channel);
CREATE INDEX IF NOT EXISTS ix_store_orders_created_at ON store_orders (created_at);

CREATE TABLE IF NOT EXISTS store_order_items (
    id BIGSERIAL PRIMARY KEY,
    store_order_id BIGINT NOT NULL REFERENCES store_orders (id) ON DELETE CASCADE,
    variant_id BIGINT NOT NULL REFERENCES product_variants (id) ON DELETE RESTRICT,
    qty INT NOT NULL DEFAULT 1,
    price_snapshot NUMERIC(10, 2) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_store_order_items_store_order_id
    ON store_order_items (store_order_id);
CREATE INDEX IF NOT EXISTS ix_store_order_items_variant_id
    ON store_order_items (variant_id);
