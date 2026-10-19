-- Android force / soft update thresholds (admin Configuration)
ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS android_min_version TEXT NOT NULL DEFAULT '';

ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS android_latest_version TEXT NOT NULL DEFAULT '';

ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS play_store_url TEXT NOT NULL DEFAULT '';
