-- Existing rows were checked before this migration; make hardened checks fully valid.

ALTER TABLE offers VALIDATE CONSTRAINT offers_discount_value_positive;
ALTER TABLE offers VALIDATE CONSTRAINT offers_percentage_at_most_100;
ALTER TABLE offers VALIDATE CONSTRAINT offers_dates_ordered;
ALTER TABLE offers VALIDATE CONSTRAINT offers_exactly_one_target;

ALTER TABLE products VALIDATE CONSTRAINT products_buying_price_nonnegative;
ALTER TABLE products VALIDATE CONSTRAINT products_selling_price_positive;
ALTER TABLE products VALIDATE CONSTRAINT products_mrp_valid;
