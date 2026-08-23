-- Warehouse ops: bidirectional transfers (store ↔ warehouse), dispatch↔order link,
-- and Lambda/RDS-friendly lookup indexes for list + fulfill queries.

-- Stock can originate from a store (returns) as well as a warehouse.
ALTER TABLE stock_transfers
    ALTER COLUMN from_warehouse_id DROP NOT NULL;

ALTER TABLE stock_transfers
    ADD COLUMN IF NOT EXISTS from_store_id BIGINT REFERENCES stores (id) ON DELETE RESTRICT;

CREATE INDEX IF NOT EXISTS ix_stock_transfers_from_store_id
    ON stock_transfers (from_store_id);

CREATE INDEX IF NOT EXISTS ix_stock_transfers_created_at
    ON stock_transfers (created_at DESC);

CREATE INDEX IF NOT EXISTS ix_stock_transfers_status_created
    ON stock_transfers (status, created_at DESC);

-- One source + one destination. Existing WH→WH / WH→store rows stay valid.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_stock_transfers_one_source'
    ) THEN
        ALTER TABLE stock_transfers
            ADD CONSTRAINT ck_stock_transfers_one_source
            CHECK (
                (from_warehouse_id IS NOT NULL AND from_store_id IS NULL)
                OR (from_warehouse_id IS NULL AND from_store_id IS NOT NULL)
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_stock_transfers_one_destination'
    ) THEN
        ALTER TABLE stock_transfers
            ADD CONSTRAINT ck_stock_transfers_one_destination
            CHECK (
                (to_warehouse_id IS NOT NULL AND to_store_id IS NULL)
                OR (to_warehouse_id IS NULL AND to_store_id IS NOT NULL)
            );
    END IF;
END $$;

-- Link D2C dispatch to the customer order it fulfills.
ALTER TABLE dispatch_orders
    ADD COLUMN IF NOT EXISTS order_id BIGINT REFERENCES orders (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_dispatch_orders_order_id
    ON dispatch_orders (order_id);

CREATE INDEX IF NOT EXISTS ix_dispatch_orders_warehouse_status_created
    ON dispatch_orders (warehouse_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_dispatch_orders_awb
    ON dispatch_orders (awb);

-- Pending online-delivery list: delivery mode + open status, newest first.
CREATE INDEX IF NOT EXISTS ix_orders_delivery_status_created
    ON orders (delivery, status, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_orders_awb_code
    ON orders (awb_code);
