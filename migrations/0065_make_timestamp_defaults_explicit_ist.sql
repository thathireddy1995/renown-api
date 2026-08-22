-- Timestamp columns store IST wall-clock values. Make automatic defaults
-- independent of the PostgreSQL session timezone (poolers can force UTC).
DO $$
DECLARE
  r record;
BEGIN
  FOR r IN
    SELECT c.relname AS table_name, a.attname AS column_name
    FROM pg_attribute a
    JOIN pg_class c ON c.oid = a.attrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_type t ON t.oid = a.atttypid
    JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND a.attnum > 0
      AND NOT a.attisdropped
      AND t.typname = 'timestamp'
      AND pg_get_expr(d.adbin, d.adrelid) IN ('now()', 'CURRENT_TIMESTAMP')
  LOOP
    EXECUTE format(
      'ALTER TABLE %I ALTER COLUMN %I SET DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE %L)',
      r.table_name,
      r.column_name,
      'Asia/Kolkata'
    );
  END LOOP;
END $$;
