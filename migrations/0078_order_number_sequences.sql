-- Sequential web order numbers: RO-{YYYY}{NNNN} (e.g. RO-20260001).
-- One locked row per calendar year; UPDATE … RETURNING is safe across Lambdas.
CREATE TABLE IF NOT EXISTS order_number_sequences (
    year INTEGER PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')
);

-- Room for RO-YYYY + growing sequence digits.
ALTER TABLE orders
    ALTER COLUMN order_number TYPE VARCHAR(32);
