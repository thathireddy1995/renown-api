ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS app_contact_lens_images JSONB NOT NULL DEFAULT '{}'::jsonb;
