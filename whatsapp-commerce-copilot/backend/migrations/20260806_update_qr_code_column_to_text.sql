-- Repeatable migration: widen qr_code from VARCHAR to TEXT.
-- Safe to run multiple times — only alters when the column exists
-- and its data type is not already 'text'.  Preserves existing data.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'whatsapp_sessions'
          AND column_name  = 'qr_code'
          AND data_type   <> 'text'
    ) THEN
        ALTER TABLE public.whatsapp_sessions
            ALTER COLUMN qr_code TYPE TEXT;
    END IF;
END $$;
