-- Apply once to an existing PostgreSQL database before deploying this release.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS preferences TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS recently_shown_products TEXT;
