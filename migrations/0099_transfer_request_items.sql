-- A store stock request can now carry many SKUs (a "request cart").
-- transfer_requests.variant_id / qty_requested stay as the first line and the
-- total quantity so older readers keep working.
CREATE TABLE IF NOT EXISTS transfer_request_items (
    id SERIAL PRIMARY KEY,
    transfer_request_id INTEGER NOT NULL REFERENCES transfer_requests(id) ON DELETE CASCADE,
    variant_id INTEGER NOT NULL REFERENCES product_variants(id) ON DELETE RESTRICT,
    qty INTEGER NOT NULL CHECK (qty > 0)
);

CREATE INDEX IF NOT EXISTS ix_transfer_request_items_request_id
    ON transfer_request_items (transfer_request_id);
CREATE INDEX IF NOT EXISTS ix_transfer_request_items_variant_id
    ON transfer_request_items (variant_id);

INSERT INTO transfer_request_items (transfer_request_id, variant_id, qty)
SELECT tr.id, tr.variant_id, tr.qty_requested
FROM transfer_requests tr
WHERE tr.qty_requested > 0
  AND NOT EXISTS (
      SELECT 1 FROM transfer_request_items i WHERE i.transfer_request_id = tr.id
  );
