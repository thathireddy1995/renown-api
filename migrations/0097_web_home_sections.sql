-- Customer website home sections, managed from admin "Web Config → Home Sections".
-- Keys prefixed web_ belong to the website; the mobile app ignores them.
-- enabled = section visible on the website; nothing tagged = default content.
ALTER TABLE home_sections DROP CONSTRAINT IF EXISTS home_sections_item_type_check;
ALTER TABLE home_sections ADD CONSTRAINT home_sections_item_type_check
  CHECK (item_type IN ('product', 'brand', 'category', 'collection'));

INSERT INTO home_sections (key, title, subtitle, item_type, sort_order) VALUES
  ('web_top_brands', 'Top Brands', '', 'brand', 101),
  ('web_collections', 'RENOWN Collections', '', 'collection', 102),
  ('web_new_arrivals', 'New Arrivals', '', 'product', 104),
  ('web_best_sellers', 'Best Sellers', '', 'product', 105)
ON CONFLICT (key) DO NOTHING;

UPDATE home_sections SET title = 'Featured', sort_order = 103 WHERE key = 'web_featured';
