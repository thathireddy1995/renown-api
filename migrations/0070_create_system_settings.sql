-- Single-row company settings used on invoices and the admin Settings page.

CREATE TABLE IF NOT EXISTS system_settings (
    id SMALLINT PRIMARY KEY DEFAULT 1,
    brand_name VARCHAR(120) NOT NULL DEFAULT 'Renown Eye Wear',
    legal_name VARCHAR(200) NOT NULL DEFAULT 'Renown Eye Wear',
    phone VARCHAR(40) NOT NULL DEFAULT '+91 96425 12952',
    email VARCHAR(160) NOT NULL DEFAULT 'support@renowneyewear.com',
    website VARCHAR(160) NOT NULL DEFAULT 'www.renowneyewear.com',
    address_line1 VARCHAR(160) NOT NULL DEFAULT '4-88, Ramdas colony',
    address_line2 VARCHAR(160) NOT NULL DEFAULT 'Vedantha Puram, Tirupati',
    city VARCHAR(80) NOT NULL DEFAULT 'Tirupati',
    state VARCHAR(80) NOT NULL DEFAULT 'Andhra Pradesh',
    postal_code VARCHAR(12) NOT NULL DEFAULT '517508',
    country VARCHAR(60) NOT NULL DEFAULT 'India',
    gstin VARCHAR(15) NOT NULL DEFAULT '37FQKPK5154A1ZV',
    state_code VARCHAR(2) NOT NULL DEFAULT '37',
    gst_percent NUMERIC(6, 3) NOT NULL DEFAULT 5,
    sgst_percent NUMERIC(6, 3) NOT NULL DEFAULT 2.5,
    cgst_percent NUMERIC(6, 3) NOT NULL DEFAULT 2.5,
    igst_percent NUMERIC(6, 3) NOT NULL DEFAULT 5,
    created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata'),
    updated_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata'),
    CONSTRAINT ck_system_settings_singleton CHECK (id = 1)
);

INSERT INTO system_settings (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;
