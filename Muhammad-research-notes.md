# AI Agent — Market Research & Problem Validation

> **Why an AI support agent for Pakistani social commerce sellers is not just useful — it is necessary.**

---

## Table of Contents

- [The Problem](#the-problem)
- [Market Context](#market-context)
- [Who We Are Building For](#who-we-are-building-for)
- [The Pain in Numbers](#the-pain-in-numbers)
- [Why Existing Solutions Fail](#why-existing-solutions-fail)
- [Why Now](#why-now)
- [Why Our AI Agent](#why-our-ai-agent)
- [Competitive Landscape](#competitive-landscape)
- [Sources](#sources)

---

## The Problem

Pakistan's social commerce market runs almost entirely on Instagram DMs and WhatsApp. Thousands of small brand owners sell directly to buyers through these platforms — no storefront, no checkout system, no CRM. Just a phone, a catalog in their head, and an inbox that never stops.

Every seller faces the same three breaking points:

**1. The DM avalanche**
A seller with 20,000 Instagram followers can receive 80–150 DMs per day. The vast majority are identical: *"price?"*, *"size available?"*, *"COD hai?"*, *"delivery kitne din mein?"*. Every single one is answered manually, one by one, by the same person who is also packing orders, managing stock, and running their life.

**2. The midnight problem**
Buying intent in Pakistan peaks late at night — between 10pm and 1am — when sellers are asleep or unavailable. Messages go unanswered. By morning, those buyers have already ordered from a competitor. There is no system, no auto-reply, no fallback. Just lost sales the seller will never know about.

**3. The COD ghost**
Cash-on-delivery is the dominant payment method in Pakistan, accounting for over 80% of ecommerce transactions. COD orders placed through DMs frequently go unconfirmed — the seller ships, the buyer does not pick up, and the seller absorbs the return cost. Without an automated confirmation flow, this is an unavoidable leak in every seller's revenue.

---

## Market Context

### Pakistan's social commerce explosion

Pakistan's ecommerce sector has grown rapidly, with social commerce — selling directly through Instagram, Facebook, and WhatsApp — becoming the dominant channel for small and medium sellers who cannot afford or do not need a full website.

| Metric | Estimate |
|--------|----------|
| Internet users in Pakistan | 100M+ |
| Active social media users | 71M+ |
| Instagram users | 16M+ |
| Estimated Instagram sellers (fashion alone) | 50,000+ |
| Pakistan ecommerce GMV (2024) | $6B+ |
| Social commerce share of ecommerce | ~30% and growing |
| COD share of all ecommerce transactions | 80%+ |

Social commerce in Pakistan is not a trend — it is the primary retail channel for millions of buyers who trust DMs more than websites and prefer COD over digital payments.

### The SME reality

Pakistan has over 5 million registered SMEs. The majority operate without formal business software. Their operational stack is:

- WhatsApp for customer communication
- Instagram for product discovery and orders
- A notebook or memory for inventory
- Manual confirmation calls for COD orders
- No analytics, no CRM, no automation

This is not a technology gap — it is a trust and access gap. Existing tools are built for Western markets, require technical setup, assume English literacy, and cost more than the average Pakistani seller can justify without a proven ROI.

---

## Who We Are Building For

**Primary user:** A Pakistani social commerce seller — fashion, beauty, home décor, or food — with 5,000 to 100,000 Instagram followers, processing 50 to 300 COD orders per month, running their store alone or with minimal help, replying to all customer messages manually from their phone.

**They are not:**
- A large retailer with a dedicated support team
- A Daraz or Amazon seller (different platform, different problems)
- A business already using a helpdesk or CRM tool

**Their daily reality:**
- Wake up to 40+ unanswered DMs
- Spend 4–6 hours replying to the same questions
- Miss sales that came in while they were asleep
- Chase COD confirmations manually
- Have no idea what customers asked most this week
- Cannot afford to hire even a part-time assistant

---

## The Pain in Numbers

Based on seller interviews and public market data:

| Pain point | Estimated impact |
|------------|-----------------|
| Hours spent on repetitive DMs per day | 4–6 hours |
| Estimated sales lost to slow/no reply per week | 15–30% of potential orders |
| COD ghost rate (unconfirmed, uncollected orders) | 20–35% |
| Cost of one uncollected COD order (shipping + return) | PKR 300–800 |
| Monthly cost of one part-time DM assistant | PKR 20,000–35,000 |
| Sellers using any formal support tool | <5% |

A seller processing 150 orders per month with a 25% COD ghost rate loses approximately 37 orders — at an average of PKR 500 per failed delivery, that is **PKR 18,500/month in avoidable losses** before even counting missed sales from slow replies.

---

## Why Existing Solutions Fail

### Generic chatbot tools (e.g. ManyChat, Tidio)
- Designed for websites and Western platforms
- No native understanding of COD workflows
- Require technical setup beyond most sellers' comfort
- English-only interfaces
- Monthly cost in USD makes ROI unclear for PKR-revenue sellers

### Hiring a DM assistant
- Costs PKR 20,000–35,000/month minimum
- Still makes mistakes on prices and stock
- Unavailable at night
- Requires constant training as catalog changes
- Not scalable as the business grows

### Instagram's built-in auto-reply
- Only sends one fixed message — no intelligence
- Cannot answer product-specific questions
- Does not handle COD confirmation
- Does not integrate with WhatsApp

### No solution exists that:
- Grounds answers in the seller's actual catalog (no hallucinated prices)
- Works across both WhatsApp and Instagram
- Handles the full COD confirmation flow
- Understands Pakistani social commerce context
- Is priced in PKR with a clear per-sale ROI

---

## Why Now

Three forces have converged in 2025–2026 that make this the right moment to build our AI Agent:

**1. AI can now do this reliably**
RAG (Retrieval-Augmented Generation) technology allows an AI agent to answer questions grounded in a specific seller's catalog — not from general knowledge. This means it will never invent a price or confirm a product that does not exist. This capability was not production-ready or affordable at scale two years ago.

**2. WhatsApp and Instagram APIs are mature**
Both platforms now offer stable, documented APIs for message automation. WhatsApp Business API (via Twilio, 360dialog) and Meta's Instagram Graph API make it technically feasible to build a reliable agent that operates on these platforms without violating terms of service.

**3. Pakistani sellers are ready**
The post-COVID ecommerce surge permanently shifted buyer behavior toward social channels. Sellers who grew 3–5x during 2020–2023 are now hitting a ceiling — they cannot grow further without operational help. The question is no longer *should I automate?* but *what is available that I can actually use?*

---

## Why Our AI Agent

Our AI Agent is built around three principles that existing tools ignore:

**Ground truth over generative guessing**
Every reply is grounded in the seller's actual catalog and policies via RAG. The agent cannot invent a price or confirm stock that does not exist. Trust is the product — one hallucinated answer destroys it.

**Built for how Pakistani commerce actually works**
COD confirmation, Urdu/English code-switching, WhatsApp-first customer behavior, Instagram DM ordering — these are not edge cases in our product. They are the core use cases.

**The seller stays in control**
Smart escalation means the agent knows when to step back. Complaints, unusual requests, and sensitive situations are immediately flagged to the seller with full context. The agent handles volume; the seller handles relationships.

---

## Competitive Landscape

| | Our AI Agent | ManyChat | Hiring assistant | Instagram auto-reply |
|---|---|---|---|---|
| Answers from real catalog | ✅ | ❌ | ⚠️ Sometimes | ❌ |
| Works on WhatsApp | ✅ | ❌ | ✅ | ❌ |
| Works on Instagram DMs | ✅ | ✅ | ✅ | ✅ |
| COD confirmation flow | ✅ | ❌ | ⚠️ Manual | ❌ |
| 24/7 availability | ✅ | ✅ | ❌ | ✅ |
| Urdu/English support | ✅ | ❌ | ✅ | ❌ |
| Daily digest for seller | ✅ | ❌ | ❌ | ❌ |
| Smart escalation | ✅ | ❌ | ✅ | ❌ |
| Priced for Pakistani SMEs | ✅ | ❌ | ⚠️ Expensive | Free |
| No technical setup needed | ✅ | ❌ | ✅ | ✅ |

---

## Sources

- Pakistan Telecommunication Authority (PTA) — Digital Pakistan Report 2024
- Statista — Pakistan ecommerce market size and forecasts
- Meta — Instagram and WhatsApp user data for Pakistan
- World Bank — Pakistan SME sector overview
- Sequoia Capital — *Services as the new software* (2024)
- Y Combinator — Requests for Startups: AI-native services (2024)
- a16z — *Top 100 Gen AI Consumer Apps* (2024)
- a16z — *AI Voice Agents* analysis (2024)
- State Bank of Pakistan — Digital payments and COD transaction data
- Primary research — seller interviews conducted by our team, June–July 2026
