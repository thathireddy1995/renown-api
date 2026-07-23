-- Delivery mode + pickup store for ecommerce orders (ship vs store pickup).
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS delivery VARCHAR(20) NOT NULL DEFAULT 'ship';

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS pickup_store_id INTEGER NULL
    REFERENCES stores(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_orders_pickup_store_id ON orders (pickup_store_id);
CREATE INDEX IF NOT EXISTS ix_orders_delivery ON orders (delivery);
