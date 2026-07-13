-- Customers table for storefront phone OTP authentication (login identifier = phone).

CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120),
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(160),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_customers_phone ON customers (phone);
CREATE INDEX IF NOT EXISTS ix_customers_email ON customers (email);
