# AI Handoff

> Last updated: 2026-07-28T13:38:00+05:00
> Status: All milestones complete. Transport migrated from whatsapp-web.js to Evolution API v2.3.7.

## Product Objective

Multi-store WhatsApp AI sales assistant. Stores connect WhatsApp accounts, customers message, AI responds with grounded product/policy info from that store's catalog.

## Architecture

Three services + DB + dashboard:
- **Backend** (Python/FastAPI :8000) — all business logic
- **Gateway Adapter** (Node.js/Express :3001) — WhatsApp transport adapter (calls Evolution API)
- **Evolution API** (Baileys-based :8080) — WhatsApp protocol engine (self-hosted, v2.3.7)
- **Dashboard** (React/Vite :5173) — seller UI
- **PostgreSQL** (:5432) — primary DB (SQLite for tests)
- **Redis** (:6379) — cache for Evolution API

## Folder Structure

```
whatsapp-commerce-copilot/
├── backend/app/          # FastAPI application
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   ├── routers/          # API routes
│   └── scripts/          # Seed, migrations
├── backend/tests/        # Pytest test suite
├── whatsapp-gateway/src/ # Node.js Evolution API adapter
│   ├── index.js          # Express entry point
│   ├── config.js         # Environment configuration
│   ├── routes.js         # Express routes (same shapes as before)
│   ├── evolution-client.js # Evolution API HTTP client
│   └── webhook-handler.js # Webhook receiver for Evolution API events
├── dashboard/src/        # React dashboard
└── docs/                 # Documentation
```

## How to Run

```bash
# Backend only (demo mode — no WhatsApp needed)
cd backend && pip install -r requirements.txt
python -m app.scripts.seed_demo
uvicorn app.main:app --port 8000

# Gateway adapter (requires Evolution API running on :8080)
cd whatsapp-gateway && npm install && npm start

# Evolution API (separate service, see docs/SETUP_AND_RUN.md)
```

## Env Vars

See `.env.example`. Key: `DATABASE_URL`, `AI_PROVIDER`, `INTERNAL_SERVICE_TOKEN`, `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`, `GATEWAY_URL`.

## Core Processing Flow

Message → Normalize → Detect Language → Detect Intent → Extract Entities → Search Catalog (store-scoped) → Match Policies → Build Response (grounded) → [Optional AI phrasing] → Reply

## What's Working

- Full project (all milestones complete)
- Evolution API transport layer (v2.3.7)
- Demo simulator (bypasses WhatsApp entirely)

## What's Partial

Nothing.

## What's Not Started

Nothing.

## Known Bugs

None.

## Tests

Backend pytest suite (110 tests) — run with:
```bash
cd backend && ./venv/bin/python -m pytest tests/ -v --tb=short
```

## Next Tasks

See docs/NEXT_STEPS.md.

## Files to Read First

1. `backend/app/services/message_processor.py` — pipeline orchestrator
2. `backend/app/services/catalog_search.py` — product matching
3. `backend/app/models/` — all DB models
4. `whatsapp-gateway/src/evolution-client.js` — Evolution API integration
5. `whatsapp-gateway/src/webhook-handler.js` — webhook event processing
6. `docs/DECISIONS.md` — design decisions

## Files Not to Change Casually

- `backend/app/models/` — DB schema changes need migration
- `backend/app/services/catalog_search.py` — heavily tested matching logic
- `backend/app/routers/internal.py` — gateway adapter depends on these exact route shapes
