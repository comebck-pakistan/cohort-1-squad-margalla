# Testing

## Run Tests

```bash
cd backend
python -m pytest tests/ -v --tb=short
```

## Test Coverage Areas

- Store isolation
- Exact SKU match
- Alias match
- Product + color query
- Product + size query
- Multi-word colors (off white, sky blue)
- Hyphenated colors (off-white)
- Quantity vs size disambiguation
- Multiple requested fields
- COD/delivery policy answers
- Unknown product
- Ambiguous product (clarification)
- Conversation follow-up
- Human takeover disabling AI
- Order confirmation
- Duplicate WhatsApp message ID
- Invalid AI JSON fallback
- Internal API auth
- Empty message validation

## Test Inputs

```
Sky blue kurta medium size mein available hai?
Navy blue sneakers size 42 ki price?
Off white kurta hai?
I want 2 pieces in size 40.
COD hai aur delivery kitne din mein hogi?
Woh black wala medium mein kitne ka hai?
```

## Latest Results

See [CURRENT_STATUS.md](CURRENT_STATUS.md).
