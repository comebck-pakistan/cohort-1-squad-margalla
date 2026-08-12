-- Migration 001: seller-managed categories + product.category_id + conversation browse state
--
-- Safe and idempotent. Preserves all existing products/data. Never drops tables,
-- columns, or volumes. Re-runnable (IF NOT EXISTS guards throughout).
--
-- Apply against the running Postgres:
--   docker compose exec -T postgres psql -U postgres -d whatsapp_commerce \
--     -f - < backend/migrations/001_categories_and_browse_state.sql
--
-- Note: on a FRESH database SQLAlchemy create_all() (run at backend startup)
-- creates the `categories` table automatically, but it never ALTERs the existing
-- `products` / `conversations` tables — so this migration is required for any
-- database that already has data.

BEGIN;

-- 1. Categories table (matches app.models.category.Category).
CREATE TABLE IF NOT EXISTS categories (
    id            VARCHAR(64)  PRIMARY KEY,
    store_id      VARCHAR(64)  NOT NULL REFERENCES stores(id),
    name          VARCHAR(100) NOT NULL,
    description   TEXT,
    image_url     VARCHAR(500),
    display_order INTEGER      NOT NULL DEFAULT 0,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at    TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_categories_store_name UNIQUE (store_id, name)
);
CREATE INDEX IF NOT EXISTS ix_categories_store_id ON categories (store_id);

-- 2. Structured category on products (nullable → existing products stay valid).
ALTER TABLE products ADD COLUMN IF NOT EXISTS category_id VARCHAR(64) REFERENCES categories(id);
CREATE INDEX IF NOT EXISTS ix_products_category_id ON products (category_id);

-- 3. Conversation category-browse state.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS category_menu_snapshot TEXT;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS browse_category_id VARCHAR(64);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS browse_offset INTEGER NOT NULL DEFAULT 0;

COMMIT;
