-- Deferred Phase 2 FKs now that brands/categories exist.
-- Clear orphaned ids first so the constraint can apply cleanly before/after seed.

UPDATE products
SET brand_id = NULL
WHERE brand_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM brands b WHERE b.id = products.brand_id);

UPDATE products
SET category_id = NULL
WHERE category_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM categories c WHERE c.id = products.category_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_brand_id'
    ) THEN
        ALTER TABLE products
            ADD CONSTRAINT fk_products_brand_id
            FOREIGN KEY (brand_id) REFERENCES brands (id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_category_id'
    ) THEN
        ALTER TABLE products
            ADD CONSTRAINT fk_products_category_id
            FOREIGN KEY (category_id) REFERENCES categories (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_products_brand_id ON products (brand_id);
CREATE INDEX IF NOT EXISTS ix_products_category_id ON products (category_id);
