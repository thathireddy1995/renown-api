-- 0070 originally used TIMESTAMPTZ. Align with the rest of the schema
-- (naive IST wall-clock). Skip if 0070 already created TIMESTAMP columns.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'system_settings'
          AND column_name = 'created_at'
          AND data_type = 'timestamp with time zone'
    ) THEN
        ALTER TABLE system_settings
            ALTER COLUMN created_at TYPE TIMESTAMP
                USING (created_at AT TIME ZONE 'Asia/Kolkata'),
            ALTER COLUMN created_at SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata'),
            ALTER COLUMN updated_at TYPE TIMESTAMP
                USING (updated_at AT TIME ZONE 'Asia/Kolkata'),
            ALTER COLUMN updated_at SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata');
    END IF;
END $$;
