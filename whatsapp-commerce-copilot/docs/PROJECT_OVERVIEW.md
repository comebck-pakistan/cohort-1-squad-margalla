# Project Overview

Multi-store WhatsApp AI sales assistant. See [ARCHITECTURE.md](ARCHITECTURE.md) for system design.

## Product Goals

1. Store owners connect their WhatsApp accounts
2. Customers message the store's WhatsApp number
3. AI responds with grounded product/policy information
4. Orders collected via conversational state machine
5. Human handoff when AI confidence is low

## Key Principles

- **Store isolation**: Every data access scoped to store_id
- **Grounded responses**: LLM never invents data; only formats pre-fetched catalog/policy info
- **Rule-first**: Deterministic pipeline handles simple cases without LLM
- **Multi-language**: English, Roman Urdu, Urdu script, mixed
