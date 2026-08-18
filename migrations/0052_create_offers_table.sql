-- Admin Offers management table
-- Supports product-level, brand-level, category-level, and gender-level offers
-- Soft delete via status; status auto-determined by dates

CREATE TABLE IF NOT EXISTS offers (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(220) NOT NULL UNIQUE,
    
    -- Discount configuration
    discount_type VARCHAR(20) NOT NULL, -- 'FLAT' or 'PERCENTAGE'
    discount_value NUMERIC(10, 2) NOT NULL,
    maximum_discount NUMERIC(10, 2), -- Max discount for percentage-based offers
    
    -- Apply offer on configuration
    apply_on VARCHAR(20) NOT NULL, -- 'PRODUCT', 'BRAND', 'CATEGORY', 'GENDER'
    product_id BIGINT, -- FK to products (when apply_on = 'PRODUCT')
    brand_id BIGINT, -- FK to brands (when apply_on = 'BRAND')
    category_id BIGINT, -- FK to categories (when apply_on = 'CATEGORY')
    gender VARCHAR(20), -- ('MALE', 'FEMALE', 'UNISEX') when apply_on = 'GENDER'
    
    -- Scheduling
    start_date TIMESTAMPTZ NOT NULL,
    end_date TIMESTAMPTZ NOT NULL,
    
    -- Priority for multi-offer scenarios
    priority INT NOT NULL DEFAULT 0,
    
    -- Status: 'scheduled', 'active', 'expired', 'inactive', 'deleted'
    -- Auto-determined except when manually deactivated (inactive)
    status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
    
    -- Audit fields
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS ix_offers_status ON offers (status);
CREATE INDEX IF NOT EXISTS ix_offers_apply_on ON offers (apply_on);
CREATE INDEX IF NOT EXISTS ix_offers_product_id ON offers (product_id);
CREATE INDEX IF NOT EXISTS ix_offers_brand_id ON offers (brand_id);
CREATE INDEX IF NOT EXISTS ix_offers_category_id ON offers (category_id);
CREATE INDEX IF NOT EXISTS ix_offers_gender ON offers (gender);
CREATE INDEX IF NOT EXISTS ix_offers_priority ON offers (priority DESC);
CREATE INDEX IF NOT EXISTS ix_offers_dates ON offers (start_date, end_date);
