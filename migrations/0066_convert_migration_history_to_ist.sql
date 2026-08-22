-- schema_migrations.applied_at was always a naive timestamp, so migration 0064's
-- timestamptz conversion could not adjust records written by earlier UTC sessions.
UPDATE schema_migrations
SET applied_at = applied_at + INTERVAL '5 hours 30 minutes'
WHERE name < '0064_store_all_timestamps_as_ist.sql';
