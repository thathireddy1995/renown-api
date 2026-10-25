-- Admin-tagged products for the customer website's "Featured" home section.
-- Nothing tagged (or section disabled) keeps the default: first 8 active products.
INSERT INTO home_sections (key, title, subtitle, item_type, sort_order) VALUES
  ('web_featured', 'Website · Featured', '', 'product', 100)
ON CONFLICT (key) DO NOTHING;
