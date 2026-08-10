-- Public invoice verify token — random UUID per order, embedded in the invoice
-- QR code. Public endpoint /public/invoice/{token} returns limited details.

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS verify_token VARCHAR(36) NULL;

-- Backfill existing rows with random UUIDs (Postgres 13+ has gen_random_uuid()
-- in core; older versions need `CREATE EXTENSION pgcrypto`).
UPDATE orders
  SET verify_token = gen_random_uuid()::text
  WHERE verify_token IS NULL;

ALTER TABLE orders
  ALTER COLUMN verify_token SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_orders_verify_token
  ON orders (verify_token);
