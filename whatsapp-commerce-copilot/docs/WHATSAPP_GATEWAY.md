# WhatsApp Gateway

Transport-only Node.js adapter service. Zero business logic.

## Transport Engine

**Evolution API v2.3.7** (Baileys-based, self-hosted) — replaces the previous whatsapp-web.js + Puppeteer approach. Evolution API runs as a separate service that manages the WhatsApp protocol connection via Baileys. This adapter sits between Evolution API and the backend, translating webhook events and REST calls.

## Architecture

```
Dashboard/Backend → Adapter (:3001) → Evolution API (:8080) → WhatsApp
                           ↑
                  Webhook callbacks
```

## Responsibilities

- Receive "connect" requests from backend → call Evolution API to create/start an instance
- Receive webhook callbacks from Evolution API (QR codes, connection state, incoming messages)
- Normalize incoming messages to the backend's InternalMessageRequest schema
- Forward normalized messages to backend POST /internal/whatsapp/messages
- Expose /send endpoint for backend to send replies (proxied to Evolution API)
- Report session status changes to backend POST /internal/whatsapp/session-events
- Cache QR codes from webhook events for polling by dashboard

## Evolution API Instance Naming

Each store gets one instance named `{store_id}`. Instance names are used to route messages and status events to the correct store.

## Webhook Events

Evolution API is configured to send these events to `POST /webhook/evolution`:

| Event | Adapter Action |
|-------|---------------|
| `QRCODE_UPDATED` | Cache QR base64, report `waiting_for_qr` to backend |
| `CONNECTION_UPDATE` | Map state (`open`→`connected`, `connecting`→`initializing`, `close`→`disconnected`), report to backend |
| `MESSAGES_UPSERT` | Filter noise/history, normalize phone/LID identity, POST to backend |

### Verified Webhook Payload Shapes (Evolution API v2.3.7)

**QRCODE_UPDATED:**
```json
{
  "event": "qrcode.updated",
  "instance": "store-id",
  "data": {
    "qrcode": {
      "code": "2@ABC123...",
      "base64": "data:image/png;base64,iVBORw0KGgo..."
    }
  },
  "apikey": "your-api-key"
}
```

**CONNECTION_UPDATE:**
```json
{
  "event": "connection.update",
  "instance": "store-id",
  "data": {
    "connection": "open"
  },
  "apikey": "your-api-key"
}
```

**MESSAGES_UPSERT:**
```json
{
  "event": "messages.upsert",
  "instance": "store-id",
  "data": {
    "key": {
      "remoteJid": "923001234567@s.whatsapp.net",
      "fromMe": false,
      "id": "3EB0XXXXXXXXXXXX"
    },
    "message": {
      "conversation": "Hello from WhatsApp!"
    }
  },
  "apikey": "your-api-key"
}
```

## Status Flow

```
disconnected → initializing → waiting_for_qr → connected
                                                    ↓
                                              disconnected
                                                    ↓
                                                 failed
```

## Webhook Security

- Evolution API includes the `apikey` field in every webhook payload
- Adapter validates this matches the configured `EVOLUTION_API_KEY`
- Custom `X-Webhook-Secret` header also set during instance creation
- In production: bind Evolution API to internal network only

## Idempotency

- The adapter keeps a bounded in-memory fast-path set and only marks a message
  after backend processing and reply delivery succeed.
- The backend stores `whatsapp_message_id` under a database unique index and
  returns the original processed response on a retry.
- Apply `backend/migrations/20260730_add_message_idempotency.sql` to databases
  that predate this change.

## Inbound Filtering

The adapter rejects groups (`@g.us`), status/broadcast/newsletter traffic,
history-sync appends, reactions, protocol/key-distribution messages, stale
messages, and unsupported media without captions. `remoteJidAlt` is preferred
when Evolution supplies an opaque WhatsApp LID. Tune the live-message window
with `MAX_INBOUND_AGE_SECONDS` (default: 300).

## Internal API

See [API_REFERENCE.md](API_REFERENCE.md) for /internal/* routes (unchanged from before).

## Gateway Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check + Evolution API reachability |
| POST | /sessions/:storeId/connect | Create/connect WhatsApp instance |
| GET | /sessions/:storeId/status | Get connection state |
| GET | /sessions/:storeId/qr | Get cached QR code |
| DELETE | /sessions/:storeId | Disconnect/delete instance |
| POST | /send | Send message (called by backend) |
| POST | /webhook/evolution | Evolution API webhook receiver |

## Limitations

See [SECURITY_AND_LIMITATIONS.md](SECURITY_AND_LIMITATIONS.md).
