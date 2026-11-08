-- Ship several home-delivery orders from one customer in a single parcel.
-- A clubbed order points at the order that carries the shared Shiprocket
-- booking; it inherits that order's AWB, courier and tracking status.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS clubbed_into_id INTEGER NULL
        REFERENCES orders(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_orders_clubbed_into_id
    ON orders (clubbed_into_id)
    WHERE clubbed_into_id IS NOT NULL;
