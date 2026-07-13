CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    order_number VARCHAR(20) NOT NULL,
    customer_id BIGINT NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    address_id BIGINT REFERENCES addresses (id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'placed',
    subtotal NUMERIC(10, 2),
    discount NUMERIC(10, 2) NOT NULL DEFAULT 0,
    shipping_fee NUMERIC(10, 2) NOT NULL DEFAULT 0,
    tax NUMERIC(10, 2) NOT NULL DEFAULT 0,
    total NUMERIC(10, 2) NOT NULL,
    coupon_code VARCHAR(30),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_order_number ON orders (order_number);
CREATE INDEX IF NOT EXISTS ix_orders_customer_id ON orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders (status);
