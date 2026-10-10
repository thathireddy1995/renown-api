-- Mobile app maintenance mode (admin Settings → Mobile app)
ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS app_maintenance_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS app_maintenance_message TEXT NOT NULL DEFAULT '';
