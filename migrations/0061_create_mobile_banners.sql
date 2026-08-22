CREATE TABLE IF NOT EXISTS mobile_banners (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    subtitle VARCHAR(300) NOT NULL DEFAULT '',
    media_url TEXT NOT NULL,
    media_key VARCHAR(500) NOT NULL,
    media_type VARCHAR(20) NOT NULL DEFAULT 'image',
    media_alt VARCHAR(200) NOT NULL DEFAULT '',
    cta_label VARCHAR(60) NOT NULL DEFAULT 'Shop Now',
    category VARCHAR(120),
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT mobile_banners_sort_order_nonnegative CHECK (sort_order >= 0),
    CONSTRAINT mobile_banners_media_type_check CHECK (media_type IN ('image', 'gif', 'video'))
);

CREATE INDEX IF NOT EXISTS ix_mobile_banners_active_order
    ON mobile_banners (is_active, sort_order, id);
