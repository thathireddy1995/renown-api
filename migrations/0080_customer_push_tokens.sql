-- FCM device tokens for customer app push notifications (one row per device).
CREATE TABLE IF NOT EXISTS customer_push_tokens (
  id SERIAL PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
  token VARCHAR(512) NOT NULL,
  platform VARCHAR(20) NOT NULL DEFAULT 'android',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_push_tokens_token
  ON customer_push_tokens (token);

CREATE INDEX IF NOT EXISTS ix_customer_push_tokens_customer_id
  ON customer_push_tokens (customer_id);
