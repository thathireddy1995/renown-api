-- Checkout coupons: named codes with schedule, targeting, and usage limits.
-- Soft-delete via status. Live codes are unique among non-deleted rows.

CREATE TABLE IF NOT EXISTS coupons (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(30) NOT NULL,

    discount_type VARCHAR(20) NOT NULL,
    discount_value NUMERIC(10, 2) NOT NULL,
    maximum_discount NUMERIC(10, 2),
    min_order_amount NUMERIC(10, 2) NOT NULL DEFAULT 0,

    apply_on VARCHAR(20) NOT NULL DEFAULT 'ALL',
    brand_id BIGINT REFERENCES brands (id) ON DELETE SET NULL,
    category_id BIGINT REFERENCES categories (id) ON DELETE SET NULL,
    gender VARCHAR(20),

    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,

    usage_limit INTEGER,
    per_customer_limit INTEGER,
    used_count INTEGER NOT NULL DEFAULT 0,

    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by BIGINT REFERENCES users (id) ON DELETE SET NULL,
    updated_by BIGINT REFERENCES users (id) ON DELETE SET NULL,

    CONSTRAINT coupons_discount_type_check CHECK (discount_type IN ('FLAT', 'PERCENTAGE')),
    CONSTRAINT coupons_apply_on_check CHECK (apply_on IN ('ALL', 'BRAND', 'CATEGORY', 'GENDER')),
    CONSTRAINT coupons_status_check CHECK (status IN ('scheduled', 'active', 'expired', 'inactive', 'deleted')),
    CONSTRAINT coupons_discount_value_positive CHECK (discount_value > 0),
    CONSTRAINT coupons_percentage_at_most_100 CHECK (discount_type <> 'PERCENTAGE' OR discount_value <= 100),
    CONSTRAINT coupons_dates_ordered CHECK (end_date > start_date),
    CONSTRAINT coupons_min_order_nonnegative CHECK (min_order_amount >= 0),
    CONSTRAINT coupons_usage_limit_positive CHECK (usage_limit IS NULL OR usage_limit > 0),
    CONSTRAINT coupons_per_customer_positive CHECK (per_customer_limit IS NULL OR per_customer_limit > 0),
    CONSTRAINT coupons_used_count_nonnegative CHECK (used_count >= 0),
    CONSTRAINT coupons_exactly_one_target CHECK (
        (apply_on = 'ALL' AND brand_id IS NULL AND category_id IS NULL AND gender IS NULL)
        OR (apply_on = 'BRAND' AND brand_id IS NOT NULL AND category_id IS NULL AND gender IS NULL)
        OR (apply_on = 'CATEGORY' AND brand_id IS NULL AND category_id IS NOT NULL AND gender IS NULL)
        OR (apply_on = 'GENDER' AND brand_id IS NULL AND category_id IS NULL AND gender IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_coupons_code_live
    ON coupons (code)
    WHERE status <> 'deleted';

CREATE INDEX IF NOT EXISTS ix_coupons_status ON coupons (status);
CREATE INDEX IF NOT EXISTS ix_coupons_dates ON coupons (start_date, end_date);
CREATE INDEX IF NOT EXISTS ix_coupons_enabled_schedule
    ON coupons (start_date, end_date)
    WHERE status NOT IN ('inactive', 'deleted');
CREATE INDEX IF NOT EXISTS ix_coupons_brand_id ON coupons (brand_id);
CREATE INDEX IF NOT EXISTS ix_coupons_category_id ON coupons (category_id);

CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id BIGSERIAL PRIMARY KEY,
    coupon_id BIGINT NOT NULL REFERENCES coupons (id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    order_id BIGINT REFERENCES orders (id) ON DELETE SET NULL,
    discount_amount NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT coupon_redemptions_discount_nonnegative CHECK (discount_amount >= 0),
    CONSTRAINT coupon_redemptions_order_unique UNIQUE (coupon_id, order_id)
);

CREATE INDEX IF NOT EXISTS ix_coupon_redemptions_coupon_customer
    ON coupon_redemptions (coupon_id, customer_id);
CREATE INDEX IF NOT EXISTS ix_coupon_redemptions_customer_id
    ON coupon_redemptions (customer_id);
