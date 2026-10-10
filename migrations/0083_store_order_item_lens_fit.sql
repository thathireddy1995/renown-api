-- Counter orders can now hold several frames, each with its own lens / power.
ALTER TABLE store_order_items ADD COLUMN IF NOT EXISTS lens_fit JSONB;
