CREATE TABLE IF NOT EXISTS compare_items (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_compare_items_customer_product
    ON compare_items (customer_id, product_id);
CREATE INDEX IF NOT EXISTS ix_compare_items_customer_id ON compare_items (customer_id);
