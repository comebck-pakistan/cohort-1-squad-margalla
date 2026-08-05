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
- Multi-turn current-product reference and picture request
- Complete persisted order flow and idempotent confirmation
- Budget and negative attribute extraction
- Group/history/protocol/stale gateway filtering
- WhatsApp LID identity normalization
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

```bash
cd backend
python -m pytest -q
# 118 passed

cd ../whatsapp-gateway
npm test
# 4 passed
```

## Real-message Evaluation

Copy `backend/evaluation/messages.example.jsonl`, replace the synthetic turns
with anonymized merchant conversations, and label action, product, entities,
and expected disposition. Run it against a backend configured with a dedicated
test database:

```bash
cd backend
python -m app.scripts.evaluate_messages evaluation/messages.jsonl
```

The report includes action accuracy, product top-1 accuracy, entity accuracy,
answer/clarify/handoff accuracy, grounding violations, and per-turn failures.
Do not evaluate against the production database because evaluation turns are
persisted to exercise real conversation state.
