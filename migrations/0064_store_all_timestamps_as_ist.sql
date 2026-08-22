-- Store every datetime as India Standard Time wall-clock (no timestamptz / UTC).
SET TIME ZONE 'Asia/Kolkata';

DO $$
BEGIN
  EXECUTE format(
    'ALTER DATABASE %I SET timezone TO %L',
    current_database(),
    'Asia/Kolkata'
  );
EXCEPTION
  WHEN insufficient_privilege THEN
    RAISE NOTICE 'Could not ALTER DATABASE timezone; sessions still set Asia/Kolkata';
END $$;

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
    WHERE t.typname = 'timestamptz'
      AND n.nspname = 'public'
      AND c.relkind = 'r'
      AND a.attnum > 0
      AND NOT a.attisdropped
  LOOP
    EXECUTE format(
      'ALTER TABLE %I ALTER COLUMN %I TYPE timestamp WITHOUT TIME ZONE USING %I AT TIME ZONE %L',
      r.table_name,
      r.column_name,
      r.column_name,
      'Asia/Kolkata'
    );
  END LOOP;
END $$;
