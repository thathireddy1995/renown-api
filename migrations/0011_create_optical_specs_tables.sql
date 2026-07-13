-- Optical master data + optional FKs on product_variants (free-text columns kept).

CREATE TABLE IF NOT EXISTS lens_types (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    price NUMERIC(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_lens_types_name ON lens_types (name);

CREATE TABLE IF NOT EXISTS frame_types (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_frame_types_name ON frame_types (name);

CREATE TABLE IF NOT EXISTS colors (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    hex VARCHAR(7) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_colors_name ON colors (name);

CREATE TABLE IF NOT EXISTS sizes (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    code VARCHAR(10) NOT NULL,
    measurement VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_sizes_code ON sizes (code);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sizes_name ON sizes (name);

-- Seed master rows so backfill can resolve Phase 2 free-text values.
INSERT INTO colors (name, hex)
VALUES
    ('Tortoise', '#5a3a22'),
    ('Matte Black', '#1a1a1a'),
    ('Crystal Clear', '#e8ebee'),
    ('Champagne Gold', '#c9a84c'),
    ('Gunmetal', '#4a4f55'),
    ('Rose Gold', '#b76e79'),
    ('Navy', '#2d4a6e'),
    ('Burgundy', '#6b1f2d'),
    ('Olive', '#5d6342'),
    ('Silver', '#b8bcc1'),
    ('Black', '#111111'),
    ('Crystal', '#e6e2d8'),
    ('Amber', '#c47a3a'),
    ('Ivory', '#efe6d2')
ON CONFLICT (name) DO NOTHING;

INSERT INTO sizes (name, code, measurement)
VALUES
    ('Extra Small', 'XS', '46-48mm'),
    ('Small', 'S', '48-50mm'),
    ('Medium', 'M', '50-52mm'),
    ('Large', 'L', '52-54mm'),
    ('Extra Large', 'XL', '54-58mm'),
    ('One Size', 'OS', 'N/A')
ON CONFLICT (code) DO NOTHING;

ALTER TABLE product_variants
    ADD COLUMN IF NOT EXISTS color_id BIGINT,
    ADD COLUMN IF NOT EXISTS size_id BIGINT;

UPDATE product_variants pv
SET color_id = c.id
FROM colors c
WHERE pv.color_id IS NULL
  AND pv.color IS NOT NULL
  AND lower(pv.color) = lower(c.name);

UPDATE product_variants pv
SET size_id = s.id
FROM sizes s
WHERE pv.size_id IS NULL
  AND pv.size IS NOT NULL
  AND (
      lower(pv.size) = lower(s.code)
      OR lower(pv.size) = lower(s.name)
  );

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_product_variants_color_id'
    ) THEN
        ALTER TABLE product_variants
            ADD CONSTRAINT fk_product_variants_color_id
            FOREIGN KEY (color_id) REFERENCES colors (id);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_product_variants_size_id'
    ) THEN
        ALTER TABLE product_variants
            ADD CONSTRAINT fk_product_variants_size_id
            FOREIGN KEY (size_id) REFERENCES sizes (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_product_variants_color_id ON product_variants (color_id);
CREATE INDEX IF NOT EXISTS ix_product_variants_size_id ON product_variants (size_id);
