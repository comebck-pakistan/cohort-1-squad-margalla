# Database Schema

Target: PostgreSQL 15 via Docker. SQLite fallback for tests.

## Tables

| Table | Key Columns | Store-Scoped |
|-------|------------|-------------|
| stores | id, business_name, owner_name, preferred_language, ai_enabled, whatsapp_status | N/A (root) |
| whatsapp_sessions | id, store_id, status, phone_number, session_data_path | Yes |
| products | id, store_id, name, category, sku, description, base_price, is_active | Yes |
| product_aliases | id, product_id, alias | Via product |
| product_variants | id, product_id, color, size, price, stock, sku | Via product |
| store_policies | id, store_id, policy_type, policy_value | Yes |
| customers | id, store_id, phone_number, name, address, city | Yes |
| conversations | id, store_id, customer_id, status, current_product_id, current_variant_id, context_json, is_ai_controlled | Yes |
| messages | id, conversation_id, direction, content, message_type, whatsapp_message_id, processed_result_json | Via conversation |
| orders | id, store_id, conversation_id, customer_id, status, total_amount | Yes |
| order_items | id, order_id, product_id, variant_id, quantity, unit_price | Via order |
| human_handoffs | id, conversation_id, store_id, reason, summary, status | Yes |

## Relationships

See SQLAlchemy models in `backend/app/models/`.
