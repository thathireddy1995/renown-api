ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS privacy_policy_url TEXT NOT NULL DEFAULT '';

ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS terms_of_service_url TEXT NOT NULL DEFAULT '';

ALTER TABLE system_settings
  ADD COLUMN IF NOT EXISTS refund_policy_url TEXT NOT NULL DEFAULT '';
