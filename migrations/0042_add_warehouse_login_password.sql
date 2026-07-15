-- Store warehouse manager portal password for admin view/edit
-- (login still uses bcrypt hash on users.password_hash).

ALTER TABLE warehouses
    ADD COLUMN IF NOT EXISTS login_password VARCHAR(255);
