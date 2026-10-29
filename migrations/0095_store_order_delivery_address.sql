-- Home-delivery orders a store places on behalf of a customer need a shipping
-- address so the warehouse can dispatch them. Pickup orders leave this null.
ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS delivery_address VARCHAR(500);
