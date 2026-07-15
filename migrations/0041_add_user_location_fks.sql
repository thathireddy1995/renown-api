-- Link staff users to a warehouse or store for location-scoped login.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS warehouse_id BIGINT REFERENCES warehouses(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS store_id BIGINT REFERENCES stores(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_users_warehouse_id ON users (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_users_store_id ON users (store_id);
