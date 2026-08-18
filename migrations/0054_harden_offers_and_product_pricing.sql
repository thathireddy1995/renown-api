-- Harden offers and three-tier product pricing after their initial rollout.

ALTER TABLE offers
    ADD COLUMN IF NOT EXISTS created_by BIGINT,
    ADD COLUMN IF NOT EXISTS updated_by BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_offers_product_id') THEN
        ALTER TABLE offers ADD CONSTRAINT fk_offers_product_id
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_offers_brand_id') THEN
        ALTER TABLE offers ADD CONSTRAINT fk_offers_brand_id
            FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_offers_category_id') THEN
        ALTER TABLE offers ADD CONSTRAINT fk_offers_category_id
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_offers_created_by') THEN
        ALTER TABLE offers ADD CONSTRAINT fk_offers_created_by
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_offers_updated_by') THEN
        ALTER TABLE offers ADD CONSTRAINT fk_offers_updated_by
            FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'offers_discount_value_positive') THEN
        ALTER TABLE offers ADD CONSTRAINT offers_discount_value_positive
            CHECK (discount_value > 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'offers_percentage_at_most_100') THEN
        ALTER TABLE offers ADD CONSTRAINT offers_percentage_at_most_100
            CHECK (discount_type <> 'PERCENTAGE' OR discount_value <= 100) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'offers_dates_ordered') THEN
        ALTER TABLE offers ADD CONSTRAINT offers_dates_ordered
            CHECK (end_date > start_date) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'offers_exactly_one_target') THEN
        ALTER TABLE offers ADD CONSTRAINT offers_exactly_one_target CHECK (
            (apply_on = 'PRODUCT' AND product_id IS NOT NULL AND brand_id IS NULL AND category_id IS NULL AND gender IS NULL)
            OR (apply_on = 'BRAND' AND product_id IS NULL AND brand_id IS NOT NULL AND category_id IS NULL AND gender IS NULL)
            OR (apply_on = 'CATEGORY' AND product_id IS NULL AND brand_id IS NULL AND category_id IS NOT NULL AND gender IS NULL)
            OR (apply_on = 'GENDER' AND product_id IS NULL AND brand_id IS NULL AND category_id IS NULL AND gender IS NOT NULL)
        ) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'products_buying_price_nonnegative') THEN
        ALTER TABLE products ADD CONSTRAINT products_buying_price_nonnegative
            CHECK (buying_price >= 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'products_selling_price_positive') THEN
        ALTER TABLE products ADD CONSTRAINT products_selling_price_positive
            CHECK (selling_price > 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'products_mrp_valid') THEN
        ALTER TABLE products ADD CONSTRAINT products_mrp_valid
            CHECK (mrp IS NULL OR (mrp > 0 AND selling_price <= mrp)) NOT VALID;
    END IF;
END $$;

DROP INDEX IF EXISTS ix_products_buying_price;
DROP INDEX IF EXISTS ix_products_selling_price;
DROP INDEX IF EXISTS ix_offers_apply_on;
DROP INDEX IF EXISTS ix_offers_gender;

CREATE INDEX IF NOT EXISTS ix_offers_enabled_schedule
    ON offers (start_date, end_date, priority DESC)
    WHERE status NOT IN ('inactive', 'deleted');
CREATE INDEX IF NOT EXISTS ix_offers_product_enabled
    ON offers (product_id, priority DESC)
    WHERE product_id IS NOT NULL AND status NOT IN ('inactive', 'deleted');
CREATE INDEX IF NOT EXISTS ix_offers_brand_enabled
    ON offers (brand_id, priority DESC)
    WHERE brand_id IS NOT NULL AND status NOT IN ('inactive', 'deleted');
CREATE INDEX IF NOT EXISTS ix_offers_category_enabled
    ON offers (category_id, priority DESC)
    WHERE category_id IS NOT NULL AND status NOT IN ('inactive', 'deleted');
CREATE INDEX IF NOT EXISTS ix_offers_gender_enabled
    ON offers (gender, priority DESC)
    WHERE gender IS NOT NULL AND status NOT IN ('inactive', 'deleted');
