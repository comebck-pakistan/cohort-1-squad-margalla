# Architecture

## Services

| Service | Tech | Port | Role |
|---------|------|------|------|
| Backend | Python/FastAPI | 8000 | All business logic, DB, AI orchestration |
| Gateway | Node.js/Express | 3001 | WhatsApp transport adapter (Evolution API) |
| Evolution API | Node.js/Baileys | 8080 | WhatsApp protocol engine (self-hosted) |
| Dashboard | React/Vite | 5173 | Seller UI |
| PostgreSQL | PostgreSQL 16 | 5432 | Primary data store |
| Redis | Redis 7 | 6379 | Cache for Evolution API |

## Data Flow

```
Customer WhatsApp Message
    → WhatsApp servers
    → Baileys (in Evolution API)
    → Evolution API webhook → POST /webhook/evolution on Gateway adapter
    → Adapter normalizes payload
    → POST /internal/whatsapp/messages (with X-Internal-Token)
    → FastAPI Backend
    → Text Normalization
    → Language Detection
    → Intent Detection
    → LangChain structured intent classification (when configured)
    → Entity Extraction
    → Catalog Search (store-scoped)
    → Policy Matching (store-scoped)
    → Response Building (grounded, traceable)
    → [Optional] LangChain grounded response chain for phrasing
    → Response returned to adapter
    → Adapter calls Evolution API sendText
    → Customer receives reply
```

## Key Design Decisions

See [DECISIONS.md](DECISIONS.md).

## Store Isolation

Every database query includes `WHERE store_id = :store_id`. No cross-store data access is possible through any API path.
