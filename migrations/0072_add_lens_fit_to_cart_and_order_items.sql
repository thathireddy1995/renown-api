-- Store power / lens-type / prescription chosen on the frame page.
ALTER TABLE cart_items
    ADD COLUMN IF NOT EXISTS lens_fit JSONB;

ALTER TABLE order_items
    ADD COLUMN IF NOT EXISTS lens_fit JSONB;
