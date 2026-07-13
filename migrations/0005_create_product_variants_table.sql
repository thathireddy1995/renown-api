-- SKU-level color/size/price/stock rows for a product.

CREATE TABLE IF NOT EXISTS product_variants (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    sku VARCHAR(40) NOT NULL,
    color VARCHAR(40),
    color_hex VARCHAR(7),
    size VARCHAR(20),
    price NUMERIC(10, 2),
    stock INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_product_variants_sku ON product_variants (sku);
CREATE INDEX IF NOT EXISTS ix_product_variants_product_id ON product_variants (product_id);
