CREATE TABLE IF NOT EXISTS appointments (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(id) ON DELETE SET NULL,
    store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE RESTRICT,
    doctor_id BIGINT REFERENCES doctors(id) ON DELETE SET NULL,
    appointment_type VARCHAR(30) NOT NULL DEFAULT 'eye_test',
    scheduled_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'booked',
    phone VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT appointments_type_check CHECK (
        appointment_type IN ('eye_test', 'fitting', 'lens_trial')
    ),
    CONSTRAINT appointments_status_check CHECK (
        status IN ('booked', 'confirmed', 'completed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS ix_appointments_store_id ON appointments (store_id);
CREATE INDEX IF NOT EXISTS ix_appointments_scheduled_at ON appointments (scheduled_at);
CREATE INDEX IF NOT EXISTS ix_appointments_status ON appointments (status);
CREATE INDEX IF NOT EXISTS ix_appointments_customer_id ON appointments (customer_id);
CREATE INDEX IF NOT EXISTS ix_appointments_doctor_id ON appointments (doctor_id);
