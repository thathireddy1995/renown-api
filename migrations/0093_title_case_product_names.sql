-- Normalize existing product names to Title Case (each word capitalized).
UPDATE products
SET name = initcap(btrim(name))
WHERE name IS NOT NULL
  AND btrim(name) <> ''
  AND name IS DISTINCT FROM initcap(btrim(name));
