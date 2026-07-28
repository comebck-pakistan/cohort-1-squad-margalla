# AI Pipeline

## Processing Flow

```
Input Message
    │
    ▼
Text Normalization (lowercase, whitespace, alias expansion)
    │
    ▼
Language Detection (keyword/heuristic — not langdetect)
    │
    ▼
Intent Detection (regex + keyword classifier)
    │
    ▼
Entity Extraction (product, color, size, quantity, SKU, requested_fields)
    │
    ▼
Catalog Search (token matching, alias, SKU, fuzzy fallback)
    │
    ▼
Policy Matching (COD, delivery, returns, exchange)
    │
    ▼
Response Building (grounded JSON with sources)
    │
    ▼
[Optional] AI Provider (phrasing only — never data invention)
    │
    ▼
Final Response
```

## Grounding Contract

The LLM never queries the database. The rule-based layer pre-fetches candidates. The LLM may only:
- Interpret language
- Extract intent
- Summarize context
- Phrase replies over the closed candidate set

Every response includes traceability (`matched_product_id`, `sources`).

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/services/text_normalizer.py` | Input normalization |
| `backend/app/services/language_detector.py` | Language identification |
| `backend/app/services/intent_detector.py` | Intent classification |
| `backend/app/services/entity_extractor.py` | Entity extraction |
| `backend/app/services/catalog_search.py` | Product search |
| `backend/app/services/policy_matcher.py` | Policy lookup |
| `backend/app/services/response_builder.py` | Response assembly |
| `backend/app/services/ai_provider.py` | AI provider abstraction |
| `backend/app/services/message_processor.py` | Pipeline orchestrator |
