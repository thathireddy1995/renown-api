-- Shiprocket shipment linkage for customer order tracking.

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS awb_code VARCHAR(80),
    ADD COLUMN IF NOT EXISTS courier_name VARCHAR(120),
    ADD COLUMN IF NOT EXISTS shiprocket_order_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS shiprocket_shipment_id VARCHAR(64),
    ADD COLUMN IF NOT EXISTS tracking_url TEXT;

CREATE INDEX IF NOT EXISTS ix_orders_awb_code ON orders (awb_code);
