-- Courier tracking webhooks look an order up by whichever identifier the
-- payload carries. awb_code already has ix_orders_awb_code; these two are the
-- fallbacks used when the AWB is absent or has been reissued.

CREATE INDEX IF NOT EXISTS ix_orders_shiprocket_order_id
    ON orders (shiprocket_order_id)
    WHERE shiprocket_order_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_orders_shiprocket_shipment_id
    ON orders (shiprocket_shipment_id)
    WHERE shiprocket_shipment_id IS NOT NULL;
