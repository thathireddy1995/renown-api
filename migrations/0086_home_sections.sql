-- Admin-managed mobile app home sections (title, visibility, tagged items).
-- items: ordered JSON array of {"id": <product/brand/category id>, "label": "", "sublabel": ""}.
CREATE TABLE IF NOT EXISTS home_sections (
  key VARCHAR(40) PRIMARY KEY,
  title VARCHAR(120) NOT NULL,
  subtitle VARCHAR(200) NOT NULL DEFAULT '',
  item_type VARCHAR(20) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INTEGER NOT NULL DEFAULT 0,
  items JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT home_sections_item_type_check CHECK (item_type IN ('product', 'brand', 'category'))
);

INSERT INTO home_sections (key, title, subtitle, item_type, sort_order) VALUES
  ('afternoon_picks', 'Afternoon Picks', '', 'product', 1),
  ('top_brands', 'Top Brands', '', 'brand', 2),
  ('deals_of_the_day', 'Deals of the Day', 'Limited time offers!', 'product', 3),
  ('best_sellers', 'Best Sellers', '', 'product', 4),
  ('brands_spotlight', 'Brands in Spotlight', '', 'brand', 5),
  ('top_value_deals', 'Top Value Deals', '', 'category', 6)
ON CONFLICT (key) DO NOTHING;
