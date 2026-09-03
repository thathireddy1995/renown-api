-- One saved prescription (power / Rx) per customer — used to prefill
-- checkout on customer web and store counter new-order flow.
CREATE TABLE IF NOT EXISTS customer_prescriptions (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    power_mode VARCHAR(20) NOT NULL DEFAULT 'powered',
    vision_type VARCHAR(40) NOT NULL DEFAULT 'single_vision',
    lens_type VARCHAR(80),
    right_sph VARCHAR(20),
    right_cyl VARCHAR(20),
    right_axis VARCHAR(20),
    right_pd VARCHAR(20),
    right_add VARCHAR(20),
    left_sph VARCHAR(20),
    left_cyl VARCHAR(20),
    left_axis VARCHAR(20),
    left_pd VARCHAR(20),
    left_add VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_customer_prescriptions_customer_id UNIQUE (customer_id),
    CONSTRAINT customer_prescriptions_power_mode_check
        CHECK (power_mode IN ('powered', 'zero'))
);

CREATE INDEX IF NOT EXISTS ix_customer_prescriptions_customer_id
    ON customer_prescriptions (customer_id);
