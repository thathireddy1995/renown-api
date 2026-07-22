-- Allow multiple frame types on a product (e.g. "Full Rim, Half Rim, Wire Frame").
ALTER TABLE products ALTER COLUMN rim_type TYPE VARCHAR(120);

-- Allow size labels that include frame type for multi-frame variants.
ALTER TABLE product_variants ALTER COLUMN size TYPE VARCHAR(80);
