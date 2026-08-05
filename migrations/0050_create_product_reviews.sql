-- Verified-purchase product reviews (Amazon-style): only customers who received
-- a delivered order containing the product may submit a rating, text, and photos.
CREATE TABLE IF NOT EXISTS product_reviews (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    customer_id BIGINT NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    order_id BIGINT REFERENCES orders (id) ON DELETE SET NULL,
    rating SMALLINT NOT NULL,
    title VARCHAR(160),
    body TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'approved',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT product_reviews_rating_check CHECK (rating >= 1 AND rating <= 5),
    CONSTRAINT product_reviews_status_check CHECK (status IN ('pending', 'approved', 'rejected')),
    CONSTRAINT product_reviews_customer_product_unique UNIQUE (customer_id, product_id)
);

CREATE INDEX IF NOT EXISTS ix_product_reviews_product_id ON product_reviews (product_id);
CREATE INDEX IF NOT EXISTS ix_product_reviews_customer_id ON product_reviews (customer_id);
CREATE INDEX IF NOT EXISTS ix_product_reviews_product_status ON product_reviews (product_id, status);

CREATE TABLE IF NOT EXISTS product_review_images (
    id BIGSERIAL PRIMARY KEY,
    review_id BIGINT NOT NULL REFERENCES product_reviews (id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_product_review_images_review_id ON product_review_images (review_id);
