CREATE TABLE IF NOT EXISTS order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products (id),
    variant_id BIGINT REFERENCES product_variants (id) ON DELETE SET NULL,
    name_snapshot VARCHAR(200),
    price_snapshot NUMERIC(10, 2),
    qty INT NOT NULL,
    CONSTRAINT order_items_qty_check CHECK (qty >= 1)
);

CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON order_items (order_id);
CREATE INDEX IF NOT EXISTS ix_order_items_product_id ON order_items (product_id);
