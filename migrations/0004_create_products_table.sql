-- Products catalog (brand_id / category_id are forward refs — FKs added in Phase 3).

CREATE TABLE IF NOT EXISTS products (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(220) NOT NULL,
    sku VARCHAR(40) NOT NULL,
    description TEXT,
    price NUMERIC(10, 2) NOT NULL,
    compare_at_price NUMERIC(10, 2),
    brand_id BIGINT,
    category_id BIGINT,
    gender VARCHAR(20),
    shape VARCHAR(30),
    material VARCHAR(30),
    rim_type VARCHAR(20),
    warranty VARCHAR(60),
    is_new BOOLEAN NOT NULL DEFAULT FALSE,
    is_bestseller BOOLEAN NOT NULL DEFAULT FALSE,
    is_trending BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_products_slug ON products (slug);
CREATE UNIQUE INDEX IF NOT EXISTS ux_products_sku ON products (sku);
CREATE INDEX IF NOT EXISTS ix_products_brand_id ON products (brand_id);
CREATE INDEX IF NOT EXISTS ix_products_category_id ON products (category_id);
CREATE INDEX IF NOT EXISTS ix_products_status ON products (status);
