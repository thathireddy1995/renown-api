-- Short "About this product" blurb (2–3 lines), separate from the long description.
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS about VARCHAR(500) NULL;
