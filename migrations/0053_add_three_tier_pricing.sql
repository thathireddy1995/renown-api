-- Add three-tier pricing structure: buying_price, mrp, selling_price
-- Migrate existing data: price → selling_price, compare_at_price → mrp

ALTER TABLE products
ADD COLUMN buying_price NUMERIC(10, 2) NOT NULL DEFAULT 0,
ADD COLUMN mrp NUMERIC(10, 2),
ADD COLUMN selling_price NUMERIC(10, 2) NOT NULL DEFAULT 0;

-- Migrate existing data
UPDATE products
SET
  selling_price = COALESCE(price, 0),
  mrp = compare_at_price,
  buying_price = 0;

-- Keep old columns for now (can deprecate later)
-- price → selling_price
-- compare_at_price → mrp

CREATE INDEX IF NOT EXISTS ix_products_buying_price ON products (buying_price);
CREATE INDEX IF NOT EXISTS ix_products_selling_price ON products (selling_price);
