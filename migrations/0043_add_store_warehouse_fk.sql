-- Link each store to a supplying warehouse (for staff login location cascade).

ALTER TABLE stores
    ADD COLUMN IF NOT EXISTS warehouse_id BIGINT REFERENCES warehouses(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_stores_warehouse_id ON stores (warehouse_id);

-- Backfill: attach stores without a warehouse to the first warehouse (if any).
UPDATE stores
SET warehouse_id = (SELECT id FROM warehouses ORDER BY id ASC LIMIT 1)
WHERE warehouse_id IS NULL
  AND EXISTS (SELECT 1 FROM warehouses);
