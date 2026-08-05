-- Apply once to an existing PostgreSQL database before deploying this release.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS preferred_response_language TEXT DEFAULT 'en';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_detected_input_language TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS language_confidence REAL DEFAULT 0.0;
