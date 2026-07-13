CREATE TABLE IF NOT EXISTS import_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_type VARCHAR(40) NOT NULL DEFAULT 'products',
    file_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    row_count INT NOT NULL DEFAULT 0,
    error_count INT NOT NULL DEFAULT 0,
    created_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT import_jobs_status_check CHECK (
        status IN ('pending', 'processing', 'completed', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS ix_import_jobs_status ON import_jobs (status);
CREATE INDEX IF NOT EXISTS ix_import_jobs_created_at ON import_jobs (created_at);
