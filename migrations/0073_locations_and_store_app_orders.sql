-- Locations + store-app order-on-behalf fields.
-- Warehouses gain an address (stores already have one).
-- Store orders gain customer phone/id, lens notes, and pickup time.

ALTER TABLE warehouses
    ADD COLUMN IF NOT EXISTS address VARCHAR(200);

ALTER TABLE store_orders
    ADD COLUMN IF NOT EXISTS customer_phone VARCHAR(20),
    ADD COLUMN IF NOT EXISTS customer_id BIGINT REFERENCES customers (id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS notes VARCHAR(500),
    ADD COLUMN IF NOT EXISTS pickup_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_store_orders_customer_phone
    ON store_orders (customer_phone);

CREATE INDEX IF NOT EXISTS ix_store_orders_customer_id
    ON store_orders (customer_id);

CREATE INDEX IF NOT EXISTS ix_store_orders_pickup_at
    ON store_orders (pickup_at);

CREATE INDEX IF NOT EXISTS ix_warehouses_code
    ON warehouses (code);

CREATE INDEX IF NOT EXISTS ix_stores_code
    ON stores (code);
