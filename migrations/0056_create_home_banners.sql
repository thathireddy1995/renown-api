CREATE TABLE IF NOT EXISTS home_banners (
    id BIGSERIAL PRIMARY KEY,
    eyebrow VARCHAR(80) NOT NULL DEFAULT '',
    title VARCHAR(160) NOT NULL,
    subtitle VARCHAR(300) NOT NULL DEFAULT '',
    brand_line VARCHAR(100) NOT NULL DEFAULT '',
    image_url TEXT NOT NULL,
    image_key VARCHAR(500) NOT NULL,
    image_alt VARCHAR(200) NOT NULL DEFAULT '',
    cta_label VARCHAR(60) NOT NULL DEFAULT 'Shop Now',
    category VARCHAR(120),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT home_banners_sort_order_nonnegative CHECK (sort_order >= 0)
);

CREATE INDEX IF NOT EXISTS ix_home_banners_active_order
    ON home_banners (is_active, sort_order, id);
