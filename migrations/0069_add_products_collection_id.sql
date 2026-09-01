-- One collection per product, matching categories. Nullable so existing
-- catalog rows stay valid until they are tagged in admin.

ALTER TABLE products
    ADD COLUMN IF NOT EXISTS collection_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_products_collection_id'
    ) THEN
        ALTER TABLE products
            ADD CONSTRAINT fk_products_collection_id
            FOREIGN KEY (collection_id) REFERENCES collections (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_products_collection_id ON products (collection_id);

-- Storefront signature lines. Skip any name/slug that already exists.
INSERT INTO collections (name, slug, status)
SELECT v.name, v.slug, 'active'
FROM (
    VALUES
        ('Classic', 'classic'),
        ('Premium', 'premium'),
        ('Signature', 'signature'),
        ('Active', 'active'),
        ('Urban', 'urban'),
        ('Minimal', 'minimal'),
        ('Kids', 'kids')
) AS v(name, slug)
WHERE NOT EXISTS (
    SELECT 1
    FROM collections c
    WHERE lower(c.slug) = v.slug
       OR lower(c.name) = lower(v.name)
);
