-- Assign sequential base SKUs starting at SKU1001 (oldest product first).
-- Two-step update avoids unique collisions while rewriting existing values.

UPDATE products SET sku = 'TMPSKU-' || id::text;

UPDATE products p
SET sku = 'SKU' || n.seq::text
FROM (
    SELECT id, 1000 + row_number() OVER (ORDER BY id ASC) AS seq
    FROM products
) n
WHERE p.id = n.id;
