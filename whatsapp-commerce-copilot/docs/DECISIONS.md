# Decisions

## Decision: Use FastAPI for core backend
**Reason:** Async-native, Pydantic-native validation, auto OpenAPI docs, excellent for API-first design.
**Alternatives rejected:** Django REST (heavier, sync-default), Flask (less structured, no native async).
**Consequences:** Requires async SQLAlchemy setup.

## Decision: SQLAlchemy 2.0 with async
**Reason:** Mature ORM, Alembic migration support, async support via asyncpg/aiosqlite.
**Alternatives rejected:** Tortoise ORM (less mature), raw SQL (unmaintainable).
**Consequences:** Slightly more boilerplate than Tortoise but better ecosystem.

## Decision: SQLite for tests, PostgreSQL for production
**Reason:** Tests run fast without external dependencies. Production needs PostgreSQL for concurrency and features.
**Consequences:** Must avoid PostgreSQL-specific SQL in models. Using aiosqlite for test DB.

## Decision: Token-based product matching with rapidfuzz fallback
**Reason:** Raw substring matching causes false positives ("red" in "embroidered"). Token matching is precise. Fuzzy fallback handles typos.
**Alternatives rejected:** Full-text search (overkill for MVP), embedding search (needs vectors).
**Consequences:** Must maintain alias lists and normalization maps.

## Decision: Keyword/heuristic language detector (not langdetect)
**Reason:** langdetect cannot detect Roman Urdu. Keyword presence (hai, mein, kya, etc.) is more reliable for this domain.
**Consequences:** May misclassify edge cases. Documented as known limitation.

## Decision: Mock AI provider as default
**Reason:** MVP must work without paid API keys. Mock provider returns structured responses using rule engine output.
**Consequences:** OpenRouter provider available via env var switch.

## Decision: React + Vite for dashboard (minimal deps)
**Reason:** Fast dev, familiar ecosystem, no Redux/complex state needed for MVP.
**Alternatives rejected:** Next.js (SSR unnecessary), plain HTML (insufficient for interactive dashboard).
**Consequences:** Simple fetch + useState/useEffect patterns.

## Decision: No JWT/session auth for MVP
**Reason:** Simplifies implementation. store_id path param + X-Internal-Token for internal routes is sufficient for demo.
**Consequences:** Must be added before any production use. Documented in SECURITY_AND_LIMITATIONS.md.

## Decision: slowapi for rate limiting
**Reason:** FastAPI-native, simple configuration, sufficient for MVP.
**Consequences:** Covers /api/demo/messages and /internal/* routes.

## Decision: Migrate WhatsApp transport from whatsapp-web.js to Evolution API v2.3.7
**Date:** 2026-07-28
**Reason:** whatsapp-web.js + Puppeteer (headless Chromium) is resource-heavy (~400MB RAM per session), fragile (breaks on WhatsApp Web internal changes), and difficult to manage at scale. Evolution API v2.3.7 (Baileys-based) provides the same unofficial-protocol capability via a RESTful API, eliminating Puppeteer entirely.
**Version pinned:** v2.3.7 (last stable before v2.4.0 licensing requirement).
**Doc source:** https://github.com/evolution-foundation/evolution-api + https://doc.evolution-api.com
**What gets deleted:** whatsapp-web.js client, Puppeteer, LocalAuth session storage, Chromium system deps in Dockerfile, all old gateway source files.
**What gets added:** Thin Node.js adapter that calls Evolution API's REST endpoints (instance create, connect, send-message) and receives webhooks (MESSAGES_UPSERT, CONNECTION_UPDATE, QRCODE_UPDATED).
**New env vars:** EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_WEBHOOK_URL, EVOLUTION_API_VERSION, GATEWAY_URL.
**Removed env vars:** GATEWAY_SESSION_PATH.
**Backend changes:** Minimal — GATEWAY_URL made configurable instead of hardcoded. No route shapes, schemas, or business logic changes.
**State mapping:** Evolution `connecting`→`initializing`, QR webhook→`waiting_for_qr`, `open`→`connected`, `close`→`disconnected`.
**Consequences:** Requires Evolution API service running (needs PostgreSQL + Redis). Same unofficial-protocol ban-risk profile as before. Gateway adapter remains transport-only with zero business logic.

## Post-Implementation Verification (2026-07-28)
**Backend tests:** 110 passed, 0 failed (2.34s) — zero regressions.
**Demo simulator:** `/api/demo/messages` works unchanged (bypasses gateway entirely).
**Gateway adapter:** Starts on :3001, health endpoint reports Evolution API reachability status.
**QR/Connection flow:** Not end-to-end tested (requires running Evolution API + real WhatsApp device).
**Divergences from plan:** None — implementation matches the migration plan exactly.
**Files deleted:** `session-manager.js`, `config.js` (old), `routes.js` (old), `index.js` (old), `Dockerfile` (old), `package.json` (old), `package-lock.json`, `node_modules/`, `.sessions/`.
**Files created:** `evolution-client.js`, `webhook-handler.js`, `config.js` (new), `routes.js` (new), `index.js` (new), `Dockerfile` (new), `package.json` (new).
**Files modified:** `backend/app/config.py` (GATEWAY_SESSION_PATH→GATEWAY_URL), `backend/app/routers/whatsapp.py` (configurable GATEWAY_URL), `.env.example`, `docker-compose.yml`, `.gitignore`, `README.md`.
**Docs updated:** WHATSAPP_GATEWAY.md, SECURITY_AND_LIMITATIONS.md, CURRENT_STATUS.md, AI_HANDOFF.md, ARCHITECTURE.md, SETUP_AND_RUN.md, DECISIONS.md.

