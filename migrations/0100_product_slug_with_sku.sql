-- Product URLs become "<name>-<category>-<sku>" (e.g. renown-reading-glass-sku1114) so same-named
-- frames get readable, stable URLs instead of renown-2, renown-3, ...
-- The previous slug is kept in legacy_slug so old links and saved
-- wishlists still resolve (the storefront redirects them to the new URL).
ALTER TABLE products ADD COLUMN IF NOT EXISTS legacy_slug VARCHAR(220) NULL;
CREATE INDEX IF NOT EXISTS ix_products_legacy_slug ON products (legacy_slug);

WITH fresh AS (
    SELECT
        p.id,
        left(
            trim(BOTH '-' FROM regexp_replace(
                lower(concat_ws('-', p.name, c.name, p.sku)), '[^a-z0-9]+', '-', 'g'
            )),
            200
        ) AS base
    FROM products p
    LEFT JOIN categories c ON c.id = p.category_id
    WHERE p.status <> 'deleted'
),
ranked AS (
    SELECT id, base, count(*) OVER (PARTITION BY base) AS dupes FROM fresh
)
UPDATE products p
SET legacy_slug = coalesce(p.legacy_slug, p.slug),
    slug = CASE WHEN r.dupes > 1 THEN r.base || '-' || p.id ELSE r.base END
FROM ranked r
WHERE p.id = r.id
  AND p.slug <> CASE WHEN r.dupes > 1 THEN r.base || '-' || p.id ELSE r.base END;
