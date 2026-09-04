-- Brand logos + category tile images for storefront carousels.
ALTER TABLE brands
  ADD COLUMN IF NOT EXISTS image VARCHAR(500);

ALTER TABLE categories
  ADD COLUMN IF NOT EXISTS image VARCHAR(500);
