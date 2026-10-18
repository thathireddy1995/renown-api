-- Ensure Reading Glasses + Eye Protection Glasses exist for storefront / APK.
INSERT INTO categories (name, slug, status, sort_order)
SELECT 'Reading Glasses', 'reading-glasses', 'active', 40
WHERE NOT EXISTS (
  SELECT 1 FROM categories WHERE lower(slug) = 'reading-glasses' OR lower(name) = 'reading glasses'
);

INSERT INTO categories (name, slug, status, sort_order)
SELECT 'Eye Protection Glasses', 'eye-protection-glasses', 'active', 45
WHERE NOT EXISTS (
  SELECT 1 FROM categories
  WHERE lower(slug) = 'eye-protection-glasses' OR lower(name) = 'eye protection glasses'
);
