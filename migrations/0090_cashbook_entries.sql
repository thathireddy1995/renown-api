-- Manual cash in / cash out entries for the admin Cashbook. Sales and refunds
-- are read live from orders / store_orders; only manual movements live here.
CREATE TABLE IF NOT EXISTS cashbook_entries (
    id SERIAL PRIMARY KEY,
    store_id INTEGER NULL REFERENCES stores(id) ON DELETE SET NULL,
    entry_date DATE NOT NULL,
    entry_type VARCHAR(3) NOT NULL,
    category VARCHAR(60) NOT NULL,
    mode VARCHAR(10) NOT NULL DEFAULT 'Cash',
    amount NUMERIC(12, 2) NOT NULL,
    note VARCHAR(500) NULL,
    entered_by_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    entered_by_name VARCHAR(120) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata'),
    CONSTRAINT ck_cashbook_entries_type CHECK (entry_type IN ('in', 'out')),
    CONSTRAINT ck_cashbook_entries_mode CHECK (mode IN ('Cash', 'UPI', 'Card', 'Bank')),
    CONSTRAINT ck_cashbook_entries_amount CHECK (amount > 0)
);

CREATE INDEX IF NOT EXISTS ix_cashbook_entries_entry_date ON cashbook_entries (entry_date);
CREATE INDEX IF NOT EXISTS ix_cashbook_entries_store_date ON cashbook_entries (store_id, entry_date);
