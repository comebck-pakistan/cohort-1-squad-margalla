-- Migration: Add ON DELETE SET NULL foreign keys to order_items
-- Make product_id nullable and add foreign keys

DO $$
BEGIN
    -- 1. Make product_id nullable
    ALTER TABLE public.order_items ALTER COLUMN product_id DROP NOT NULL;

    -- 2. Add product_id foreign key if it does not exist
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'order_items'
          AND constraint_name = 'fk_order_items_product_id'
    ) THEN
        ALTER TABLE public.order_items
            ADD CONSTRAINT fk_order_items_product_id
            FOREIGN KEY (product_id)
            REFERENCES public.products(id)
            ON DELETE SET NULL;
    END IF;

    -- 3. Add variant_id foreign key if it does not exist
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = 'public'
          AND table_name = 'order_items'
          AND constraint_name = 'fk_order_items_variant_id'
    ) THEN
        ALTER TABLE public.order_items
            ADD CONSTRAINT fk_order_items_variant_id
            FOREIGN KEY (variant_id)
            REFERENCES public.product_variants(id)
            ON DELETE SET NULL;
    END IF;
END $$;
