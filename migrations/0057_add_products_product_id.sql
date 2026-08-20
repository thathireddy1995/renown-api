-- Unique jewellery-style Product ID (HUID-like), separate from products.id / sku.
-- Nullable so existing catalog rows stay valid; uniqueness applies when set.

ALTER TABLE products
ADD COLUMN IF NOT EXISTS product_id VARCHAR(40);

CREATE UNIQUE INDEX IF NOT EXISTS ux_products_product_id ON products (product_id);
