-- ₹50 charge on home-delivery cash-on-delivery orders, kept apart from
-- shipping/platform fees so invoices and reports can show it on its own line.
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cod_fee NUMERIC(10, 2) NOT NULL DEFAULT 0;
