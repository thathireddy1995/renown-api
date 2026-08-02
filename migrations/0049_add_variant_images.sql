-- Lets each color/size variant carry its own photo set (e.g. a green frame
-- showing green photos) instead of every color sharing the product's single
-- image gallery. Empty by default — falls back to the product's images.
ALTER TABLE product_variants ADD COLUMN IF NOT EXISTS images JSONB NOT NULL DEFAULT '[]'::jsonb;
