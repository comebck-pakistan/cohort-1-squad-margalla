# Conversation and Order State

## Conversation Context

Stored per conversation:
- `current_product_id` — last discussed product
- `current_variant_id` — last discussed variant
- `selected_color`, `selected_size`
- `quantity`
- `requested_city`
- `order_stage` — current position in order state machine
- `pending_clarification` — awaiting customer choice
- `clarification_candidates` — numbered product options
- `is_ai_controlled` — AI or human mode
- `conversation_summary` — running context summary

## Order State Machine

```
BROWSING
    → PRODUCT_SELECTED
    → VARIANT_SELECTED
    → QUANTITY_SELECTED
    → CUSTOMER_DETAILS_REQUIRED
    → ADDRESS_REQUIRED
    → PAYMENT_METHOD_REQUIRED
    → ORDER_CONFIRMATION
    → ORDER_CREATED
```

Collected: name, phone, product, variant, color, size, quantity, address, city, payment method, total price.

Final summary shown before ORDER_CREATED. Explicit confirmation required.
