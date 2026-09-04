-- Controllable category display order (homepage + product filters).
ALTER TABLE categories
  ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;

-- Match the storefront filter preference: Eye → Sun → Computer → others.
UPDATE categories SET sort_order = 0 WHERE lower(name) LIKE '%eye%' AND lower(name) NOT LIKE '%computer%';
UPDATE categories SET sort_order = 1 WHERE lower(name) LIKE '%sun%';
UPDATE categories SET sort_order = 2 WHERE lower(name) LIKE '%computer%';
UPDATE categories SET sort_order = 10 WHERE lower(name) LIKE '%renospl%';
