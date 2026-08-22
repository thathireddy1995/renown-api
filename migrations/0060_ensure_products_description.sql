-- Ensure products.description exists for admin Add Product copy.
-- Original table (0004) already defined this column; this is safe to re-run.

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS description TEXT;
