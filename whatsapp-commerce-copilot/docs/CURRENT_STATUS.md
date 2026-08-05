# Current Status

> Last updated: 2026-07-30

## Status Snapshot

| Area | Status |
|------|--------|
| Project structure | ✅ Complete |
| DB models | ✅ Complete (12 models) |
| Seed data | ✅ Complete (2 stores, 8 products) |
| Conversation-aware pipeline | ✅ Connected to demo and live routes |
| Simulator endpoint | ✅ Complete |
| AI provider | ✅ Connected with closed-candidate ID validation |
| Conversation memory | ✅ Connected to live processing |
| Order workflow | ✅ Connected end-to-end, including corrections/cancel/status |
| WhatsApp gateway | ✅ Migrated to Evolution API v2.3.7 |
| QR + session APIs | ✅ Complete |
| Dashboard | ✅ Complete |
| Human handoff | ✅ Complete |
| Full test suite | ✅ Complete (118 backend + 4 gateway tests passing) |
| Docker | ✅ Updated (Evolution API + Redis services) |

## Test Suite — PASSED ✅

```
$ cd backend && ./venv/bin/python -m pytest tests/ -v --tb=short
======================= 118 passed ========================
```

## Demo Simulator — WORKING ✅

```
$ curl -s -X POST http://localhost:8000/api/demo/messages \
  -H "Content-Type: application/json" \
  -d '{"store_id":"demo-store-fashion","customer_number":"923001234567","message":"Sky blue kurta medium size mein available hai?"}'

{
    "message": "*Women's Embroidered Kurta*\n  Sky Blue | Size medium: Rs. 2,500 — Available hai (Stock: 4)",
    "intent": "stock_query",
    "confidence": 0.95,
    "matched_product_id": "prod-kurta-emb-001",
    "matched_variant_id": "var-001-sb-m",
    "sources": ["catalog:product:prod-kurta-emb-001", "inventory:variant:var-001-sb-m"],
    ...
}
```

## Gateway Adapter — RUNNING ✅

```
$ cd whatsapp-gateway && node src/index.js
{"level":"info","message":{"msg":"WhatsApp Gateway started (Evolution API adapter)","port":3001,...},"timestamp":"..."}

$ curl -s http://localhost:3001/health
{
    "status": "degraded",
    "service": "whatsapp-gateway",
    "transport": "evolution-api",
    "transportVersion": "2.3.7",
    "evolutionApiReachable": false
}
```

> [!NOTE]
> Gateway reports "degraded" because Evolution API is not running locally.
> Once Evolution API is started on :8080, status will change to "ok".

## Known Blockers

- Evolution API service must be installed and running locally for real WhatsApp connection
- Redis must be running for Evolution API
- QR → connected flow not tested (requires running Evolution API + real WhatsApp device)
- Production databases created before 2026-07-30 must apply
  `backend/migrations/20260730_add_message_idempotency.sql`
- Real-message quality still depends on collecting and anonymizing merchant
  conversations; synthetic tests cannot substitute for that dataset
