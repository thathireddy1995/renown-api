CREATE TABLE IF NOT EXISTS employees (
    id BIGSERIAL PRIMARY KEY,
    employee_code VARCHAR(40) NOT NULL,
    name VARCHAR(120) NOT NULL,
    job_role VARCHAR(40) NOT NULL,
    store_id BIGINT REFERENCES stores(id) ON DELETE SET NULL,
    warehouse_id BIGINT REFERENCES warehouses(id) ON DELETE SET NULL,
    phone VARCHAR(20),
    shift VARCHAR(20),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    mtd_sales NUMERIC(10, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT employees_status_check CHECK (status IN ('active', 'inactive'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_employees_employee_code ON employees (employee_code);
CREATE INDEX IF NOT EXISTS ix_employees_store_id ON employees (store_id);
CREATE INDEX IF NOT EXISTS ix_employees_warehouse_id ON employees (warehouse_id);
CREATE INDEX IF NOT EXISTS ix_employees_job_role ON employees (job_role);
