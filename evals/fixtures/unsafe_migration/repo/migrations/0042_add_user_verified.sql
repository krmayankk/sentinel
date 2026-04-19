-- Migration: add verified flag and email index to users table
-- Ticket: PLAT-2847

ALTER TABLE users ADD COLUMN verified BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX idx_users_email ON users(email);

ALTER TABLE users DROP COLUMN legacy_status;
