-- Brand slugs previously had to be unique across ALL brands, which blocked
-- adding a brand with a slug already used by a differently-named brand
-- (e.g. RIGA and TOMMY-HIFIGER both wanting a "sunglasses" slug). Scope the
-- uniqueness to the (name, slug) pair instead so different brands can reuse
-- the same slug, while a single brand still can't have the same slug twice.
DROP INDEX IF EXISTS ux_brands_slug;

CREATE UNIQUE INDEX IF NOT EXISTS ux_brands_name_slug ON brands (name, slug);
