-- Admin orders/customers list filters and sorts (Phase 6).
-- Skips indexes already present from 0002 / 0017.

CREATE INDEX IF NOT EXISTS ix_orders_customer_id_status
    ON orders (customer_id, status);

CREATE INDEX IF NOT EXISTS ix_orders_created_at
    ON orders (created_at);

CREATE INDEX IF NOT EXISTS ix_customers_created_at
    ON customers (created_at);

CREATE INDEX IF NOT EXISTS ix_customers_is_active
    ON customers (is_active);
