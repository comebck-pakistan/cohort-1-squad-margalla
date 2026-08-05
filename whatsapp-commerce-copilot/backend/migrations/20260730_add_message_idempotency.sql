-- Apply once to an existing PostgreSQL database before deploying this release.
-- The query intentionally fails if duplicate non-null IDs already exist; inspect
-- and resolve those rows rather than silently deleting customer history.
CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_whatsapp_id
ON messages (whatsapp_message_id)
WHERE whatsapp_message_id IS NOT NULL;
