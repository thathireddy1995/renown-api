-- Reporting indexes for aggregate date-range queries (idempotent).
-- orders.created_at and store_orders.created_at already indexed in prior phases.

CREATE INDEX IF NOT EXISTS ix_dispatch_orders_created_at
    ON dispatch_orders (created_at);

CREATE INDEX IF NOT EXISTS ix_grn_received_at
    ON grn (received_at);
