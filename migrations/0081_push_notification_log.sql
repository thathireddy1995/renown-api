-- History of push notifications sent from the admin panel.
CREATE TABLE IF NOT EXISTS push_notification_log (
  id SERIAL PRIMARY KEY,
  title VARCHAR(120) NOT NULL,
  body VARCHAR(500) NOT NULL,
  image_url VARCHAR(1000),
  audience VARCHAR(20) NOT NULL,
  customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
  sent INTEGER NOT NULL DEFAULT 0,
  failed INTEGER NOT NULL DEFAULT 0,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_push_notification_log_created_at
  ON push_notification_log (created_at DESC);
