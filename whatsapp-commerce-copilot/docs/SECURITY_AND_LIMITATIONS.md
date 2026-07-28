# Security and Limitations

## WhatsApp Automation (Critical)

This project uses [Evolution API v2.3.7](https://github.com/evolution-foundation/evolution-api), which is built on **Baileys**, an **unofficial, reverse-engineered** WhatsApp Web library.

Previously, this project used whatsapp-web.js + Puppeteer (headless Chromium). Evolution API (Baileys-based) carries the **same unofficial-protocol ban-risk profile** — no meaningful increase or decrease. The key improvement is eliminating Puppeteer-related instability and resource overhead (~400MB RAM per Chromium instance).

### Risks

1. **Terms of Service**: Using unofficial WhatsApp automation may violate WhatsApp/Meta's Terms of Service. Accounts may be banned.
2. **Stability**: Baileys depends on WhatsApp Web's internal protocol, which can change without notice, breaking the integration.
3. **No SLA**: No uptime guarantee, no official support, no security audit.
4. **Session Security**: Evolution API stores session data in its database. If compromised, an attacker can impersonate the connected WhatsApp account.

### Mitigations

- Evolution API bound to internal network (not exposed publicly)
- Gateway adapter validates webhook payloads via shared API key
- No raw credentials logged
- Evolution API session data stored in database (not filesystem)

### Migration Path

The gateway adapter is transport-only. To switch to the official Meta WhatsApp Cloud API:
1. Replace Evolution API client calls with Meta Cloud API webhook receiver
2. Update QR flow to Meta's embedded signup
3. Backend `/internal/*` routes remain unchanged
4. Gateway adapter route shapes remain the same — only the underlying transport changes

## Security Measures

| Measure | Implementation |
|---------|---------------|
| Secrets | Environment variables only, .env.example provided |
| CORS | Explicit origins from env |
| Internal auth | X-Internal-Token header on /internal/* routes |
| Input validation | Pydantic schemas on all endpoints |
| Rate limiting | slowapi on /api/demo/messages and /internal/* |
| Store isolation | store_id scoping on every query |
| No eval/exec | No dynamic code execution |
| Error handling | Safe errors, no stack trace leakage |
| Logging | Structured, excludes customer message content where unnecessary |
| Idempotency | Duplicate WhatsApp message ID detection (adapter + backend) |
| Webhook security | API key validation on Evolution API webhook payloads |

## Known Limitations

1. No JWT/session-based user authentication (MVP uses store_id path params)
2. Roman Urdu language detection is heuristic-based (langdetect fails on Roman Urdu)
3. Voice messages: architecture documented, not implemented
4. No end-to-end encryption verification
5. Dashboard has no real auth
6. Evolution API requires Redis + PostgreSQL (additional infrastructure)
