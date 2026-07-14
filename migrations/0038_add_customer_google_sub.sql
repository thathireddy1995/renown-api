-- Google Sign-In: store Google subject id; allow phone-less Google-only accounts.

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255);

ALTER TABLE customers
    ALTER COLUMN phone DROP NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_customers_google_sub
    ON customers (google_sub)
    WHERE google_sub IS NOT NULL;
