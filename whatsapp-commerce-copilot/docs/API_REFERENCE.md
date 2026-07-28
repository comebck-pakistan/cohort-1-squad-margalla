# API Reference

Base URL: `http://localhost:8000`

## Public Routes

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/health | Health check |
| POST | /api/stores | Create store |
| GET | /api/stores | List stores |
| GET | /api/stores/{store_id} | Get store |
| POST | /api/stores/{store_id}/whatsapp/connect | Initiate WhatsApp connection |
| GET | /api/stores/{store_id}/whatsapp/status | Get connection status |
| GET | /api/stores/{store_id}/whatsapp/qr | Get QR code |
| DELETE | /api/stores/{store_id}/whatsapp | Disconnect |
| GET | /api/stores/{store_id}/products | List products |
| POST | /api/stores/{store_id}/products | Create product |
| PATCH | /api/stores/{store_id}/products/{product_id} | Update product |
| GET | /api/stores/{store_id}/conversations | List conversations |
| GET | /api/stores/{store_id}/conversations/{id} | Get conversation |
| POST | /api/stores/{store_id}/conversations/{id}/takeover | Human takeover |
| POST | /api/stores/{store_id}/conversations/{id}/enable-ai | Return to AI |
| GET | /api/stores/{store_id}/orders | List orders |
| POST | /api/demo/messages | Simulator endpoint |

## Internal Routes (X-Internal-Token required)

| Method | Path | Description |
|--------|------|-------------|
| POST | /internal/whatsapp/messages | Gateway forwards incoming message |
| POST | /internal/whatsapp/send | Backend requests message send |
| POST | /internal/whatsapp/session-events | Gateway reports status changes |

## Demo Message Request

```json
{
  "store_id": "demo-store-fashion",
  "customer_number": "923001234567",
  "message": "Sky blue kurta medium size mein available hai?"
}
```

Detailed request/response schemas in `backend/app/schemas/`.
