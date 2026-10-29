-- When the customer actually received the order (delivered / collected).
-- COD cash is counted in the cashbook on this day, not the order date.
-- A trigger stamps it so every status path (admin, store app, staff app,
-- courier webhook) is covered without app code changes.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS handed_over_at TIMESTAMP NULL;
ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS handed_over_at TIMESTAMP NULL;

CREATE OR REPLACE FUNCTION stamp_handed_over_at() RETURNS trigger AS $$
BEGIN
    IF lower(coalesce(NEW.status, '')) IN ('delivered', 'collected', 'completed') THEN
        IF NEW.handed_over_at IS NULL
           OR TG_OP = 'INSERT'
           OR lower(coalesce(OLD.status, '')) NOT IN ('delivered', 'collected', 'completed') THEN
            NEW.handed_over_at := CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata';
        END IF;
    ELSE
        NEW.handed_over_at := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_orders_handed_over_at ON orders;
CREATE TRIGGER trg_orders_handed_over_at
    BEFORE INSERT OR UPDATE OF status ON orders
    FOR EACH ROW EXECUTE FUNCTION stamp_handed_over_at();

DROP TRIGGER IF EXISTS trg_store_orders_handed_over_at ON store_orders;
CREATE TRIGGER trg_store_orders_handed_over_at
    BEFORE INSERT OR UPDATE OF status ON store_orders
    FOR EACH ROW EXECUTE FUNCTION stamp_handed_over_at();

-- Best available date for orders already handed over.
UPDATE orders SET handed_over_at = updated_at
WHERE handed_over_at IS NULL AND lower(status) = 'delivered';
UPDATE store_orders SET handed_over_at = created_at
WHERE handed_over_at IS NULL AND lower(status) IN ('delivered', 'collected', 'completed');
