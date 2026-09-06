-- Unique razorpay_payment_id so verify retries cannot create duplicate paid orders.
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_razorpay_payment_id
  ON orders (razorpay_payment_id)
  WHERE razorpay_payment_id IS NOT NULL;
