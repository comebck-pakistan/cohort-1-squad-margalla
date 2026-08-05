# AI Pipeline

## Processing Flow

```
Input Message
    │
    ▼
Conversation Controller (history, current product, clarification, order stage)
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
Entity Extraction (product, color, size, quantity, SKU, budget, exclusions)
    │
    ▼
[Configured] LangChain Intent + Product Query Chain (structured Pydantic output)
    │
    ▼
Catalog Search (SKU, context ID, alias, description/category tokens,
               structured variant/price filters, fuzzy fallback)
    │
    ▼
Policy Matching (COD, delivery, returns, exchange)
    │
    ▼
Response Building (grounded JSON with sources)
    │
    ▼
[Optional] LangChain Response Chain (closed candidates only; returned IDs validated)
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
| `backend/app/services/ai_provider.py` | LangChain chains and provider abstraction |
| `backend/app/services/message_processor.py` | Pipeline orchestrator |
| `backend/app/services/conversation_controller.py` | Memory, order routing, constrained AI, handoff |

## AI Call Boundary

With `AI_PROVIDER=gemini`, every customer message is classified by a
LangChain LCEL chain with Pydantic structured output. The deterministic result
remains authoritative for retrieval and order operations. A second LangChain
chain is called only for ambiguity, unknown language, or low confidence. It
receives at most five retrieved catalogue candidates and recent history. Any
product or variant ID outside that candidate set is rejected and the
deterministic response is used instead. If no Gemini API key is configured,
both demo and live routes continue with the deterministic pipeline. For
compatibility with the original setup, the Gemini provider can also read a
key already placed in `OPENAI_API_KEY`; new installations should use
`GEMINI_API_KEY`.
