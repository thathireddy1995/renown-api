CREATE TABLE IF NOT EXISTS cart_items (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    variant_id BIGINT REFERENCES product_variants (id) ON DELETE SET NULL,
    qty INT NOT NULL DEFAULT 1,
    saved_for_later BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cart_items_qty_check CHECK (qty >= 1)
);

-- COALESCE so NULL variant_id still enforces one row per product for a customer.
CREATE UNIQUE INDEX IF NOT EXISTS ux_cart_items_customer_product_variant
    ON cart_items (customer_id, product_id, COALESCE(variant_id, 0));
CREATE INDEX IF NOT EXISTS ix_cart_items_customer_id ON cart_items (customer_id);
CREATE INDEX IF NOT EXISTS ix_cart_items_product_id ON cart_items (product_id);
