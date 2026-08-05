-- Add the optional catalogue image used by API responses and LangChain context.
-- PostgreSQL production migration. SQLite development databases can run the
-- equivalent statement without IF NOT EXISTS after checking PRAGMA table_info.
ALTER TABLE products
ADD COLUMN IF NOT EXISTS image_url VARCHAR(500);
