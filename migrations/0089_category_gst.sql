-- Per-category GST rate and HSN code (eyewear is not one rate: spectacles and
-- frames are 5%, sunglasses 18%). NULL means "use the company GST % / default HSN".
ALTER TABLE categories
  ADD COLUMN IF NOT EXISTS gst_percent NUMERIC(6, 3) NULL,
  ADD COLUMN IF NOT EXISTS hsn_code VARCHAR(8) NULL;

ALTER TABLE categories DROP CONSTRAINT IF EXISTS ck_categories_gst_percent;
ALTER TABLE categories
  ADD CONSTRAINT ck_categories_gst_percent
  CHECK (gst_percent IS NULL OR (gst_percent >= 0 AND gst_percent <= 100));
