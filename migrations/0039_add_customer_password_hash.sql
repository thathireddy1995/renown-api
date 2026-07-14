-- Mobile number + password sign-in for customers (registration flow).

ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
