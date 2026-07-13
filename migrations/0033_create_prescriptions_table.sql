CREATE TABLE IF NOT EXISTS prescriptions (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    doctor_id BIGINT REFERENCES doctors(id) ON DELETE SET NULL,
    right_sph VARCHAR(20),
    right_cyl VARCHAR(20),
    left_sph VARCHAR(20),
    left_cyl VARCHAR(20),
    pd VARCHAR(20),
    recorded_at DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_prescriptions_customer_id ON prescriptions (customer_id);
CREATE INDEX IF NOT EXISTS ix_prescriptions_doctor_id ON prescriptions (doctor_id);
