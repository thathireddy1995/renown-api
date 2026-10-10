-- Counter (store app) orders carry the same structured lens choice as web orders.
ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS lens_fit JSONB;

-- Staff-entered prescriptions: astigmatism axis, near addition and vision type.
ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS right_axis VARCHAR(20);
ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS left_axis VARCHAR(20);
ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS right_add VARCHAR(20);
ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS left_add VARCHAR(20);
ALTER TABLE prescriptions ADD COLUMN IF NOT EXISTS vision_type VARCHAR(30);
