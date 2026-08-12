-- Add pairing_code to whatsapp_sessions for phone-number linking (alongside QR).
-- PostgreSQL production migration. create_all() does NOT alter an existing table,
-- so any database created before pairing_code was added to the model needs this.
-- Safe to run repeatedly (IF NOT EXISTS). Preserves existing rows/data.
--
-- SQLite development databases: SQLite's ADD COLUMN has no IF NOT EXISTS, so run
-- the following once, guarded by a PRAGMA table_info(whatsapp_sessions) check:
--   ALTER TABLE whatsapp_sessions ADD COLUMN pairing_code VARCHAR(20);
ALTER TABLE whatsapp_sessions
ADD COLUMN IF NOT EXISTS pairing_code VARCHAR(20);
