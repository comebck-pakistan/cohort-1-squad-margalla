# Graph Report - .  (2026-08-07)

## Corpus Check
- 122 files · ~52,671 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1098 nodes · 1967 edges · 88 communities (66 shown, 22 thin omitted)
- Extraction: 73% EXTRACTED · 27% INFERRED · 0% AMBIGUOUS · INFERRED: 533 edges (avg confidence: 0.69)
- Token cost: 33,037 input · 1,664 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 72
- Community 74
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87

## God Nodes (most connected - your core abstractions)
1. `Conversation` - 64 edges
2. `Product` - 52 edges
3. `ProcessedResponse` - 41 edges
4. `t()` - 37 edges
5. `Store` - 34 edges
6. `ConversationController` - 33 edges
7. `extract_entities()` - 33 edges
8. `ProductVariant` - 30 edges
9. `normalize_text()` - 27 edges
10. `AIRequestContext` - 26 edges

## Surprising Connections (you probably didn't know these)
- `run()` --calls--> `Product`  [INFERRED]
  debug_search.py → backend/app/models/product.py
- `AI Pipeline Documentation` --references--> `Backend Service (FastAPI)`  [INFERRED]
  docs/AI_PIPELINE.md → docker-compose.yml
- `test_recently_shown_products_limit()` --calls--> `Conversation`  [INFERRED]
  backend/tests/test_contextual_improvements.py → backend/app/models/conversation.py
- `test_resolve_followup_returns_recently_shown_and_preferences()` --calls--> `Conversation`  [INFERRED]
  backend/tests/test_contextual_improvements.py → backend/app/models/conversation.py
- `conversation()` --calls--> `Conversation`  [INFERRED]
  backend/tests/test_order_workflow.py → backend/app/models/conversation.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Core Message Processing Flow** — backend_service, gateway_service, evolution_api_service [EXTRACTED 1.00]
- **Data Persistence Layer** — postgres_service, redis_service [EXTRACTED 1.00]

## Communities (88 total, 22 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (60): get_settings(), Application configuration via environment variables., Reset settings singleton (for testing)., Application settings loaded from environment variables., reset_settings(), Settings, HumanHandoff, WhatsAppSession (+52 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (29): Mock classification using standard regex rules., _extract_budget(), _extract_color(), extract_entities(), _extract_excluded_colors(), _extract_product_query(), _extract_size_and_quantity(), Entity extraction from normalized text.  Extracts: product_query, sku, category, (+21 more)

### Community 2 - "Community 2"
Cohesion: 0.05
Nodes (20): Tests for catalog search service.  Covers: exact SKU, alias, product+color, prod, Test multi-word color matching., Test hyphenated color normalization., Test unknown product handling., Test ambiguous product detection., Multiple sneakers match 'black sneakers' — should detect ambiguity., Test that search is scoped to provided products only., Test exact SKU matching. (+12 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (20): Any, Centralised multilingual message templates.  All customer-facing strings must go, Translate a message key into the requested language.      Args:         key:, t(), _lang(), Order manager — state machine for order collection.  States: BROWSING → PRODUCT_, Normalise store_language to i18n code., Get the next prompt to show customer based on order stage. (+12 more)

### Community 4 - "Community 4"
Cohesion: 0.10
Nodes (33): Base, Base class for all SQLAlchemy models., Order, OrderItem, Order and OrderItem models., Product, ProductAlias, ProductVariant (+25 more)

### Community 5 - "Community 5"
Cohesion: 0.05
Nodes (38): dependencies, axios, lucide-react, react, react-dom, devDependencies, jsdom, oxlint (+30 more)

### Community 6 - "Community 6"
Cohesion: 0.09
Nodes (32): demo_message(), AsyncSession, Request, Demo message simulator endpoint.  POST /api/demo/messages — runs the full messag, Process a demo message through the full pipeline.      This endpoint runs the sa, AsyncSession, Request, Internal routes for WhatsApp gateway communication.  Protected with X-Internal-T (+24 more)

### Community 7 - "Community 7"
Cohesion: 0.08
Nodes (27): _make_jpeg(), UploadFile.close() must be called even on success., A crafted image that triggers DecompressionBombError is rejected with 400., If db.commit() fails during create, image is cleaned up and 500 is returned., DB failure during image replace returns 500 and cleans up new image., DB failure during DELETE /{id}/image returns 500., Products with HTTP image_url must never trigger filesystem deletion., If the shared-reference query fails post-commit, the response is still success. (+19 more)

### Community 8 - "Community 8"
Cohesion: 0.10
Nodes (15): detect_language(), LanguageDetection, Language detection using keyword/heuristic classifier.  langdetect cannot reliab, Result of language detection., Detect language of input text.      Returns a LanguageDetection namedtuple with:, Simulate the logic that lives in ConversationController., Black shoes dikhao' mixes English and Roman Urdu., A bare number should be neutral — session language preserved. (+7 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (26): health_check(), _cleanup_if_unshared(), _cleanup_local_image(), create_product(), delete_product(), delete_product_image(), get_safe_filepath(), get_upload_dir() (+18 more)

### Community 10 - "Community 10"
Cohesion: 0.13
Nodes (10): ConversationController, AsyncSession, Conversation-aware controller shared by demo and WhatsApp entry points.  This is, Detect if the message promises a future action like fetching images., ProcessedResponse, Complete response from the pipeline., Convert to JSON-serializable dict., test_detect_future_action_promise() (+2 more)

### Community 11 - "Community 11"
Cohesion: 0.11
Nodes (11): detect_intent(), Intent detection via regex and keyword classification.  Detects the common actio, Detect intent from normalized text.      Supports multiple intents/requested_fie, Tests for intent detection., Test: 'Sky blue kurta available hai? Price aur COD bhi bata dein., TestGreetings, TestHumanRequest, TestMultipleFields (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.12
Nodes (18): ExtractedEntities, Extracted entities from a message., IntentResult, Result of intent detection., _lang(), Response builder — creates grounded, traceable responses.  Every response includ, Respond to non-product turns without claiming a catalogue miss., Build clarification response for ambiguous matches. (+10 more)

### Community 13 - "Community 13"
Cohesion: 0.10
Nodes (25): _post(), Tests for LLM catalog grounding and intent/query orchestration.  Each test valid, AI returns a product ID not in the candidate set → must be rejected., AI returns a variant ID not in the candidate variants → must be dropped., AI claims Rs. 9999 but authoritative price is Rs. 10 → authoritative wins., LLM classifies as order_request with 0.1 confidence → deterministic wins., LLM rewrites 'lal wala' → 'Red Kurta' → correct product matched., Query for nonexistent product → clear not-found message. (+17 more)

### Community 14 - "Community 14"
Cohesion: 0.15
Nodes (15): plugins, rules, react/only-export-components, react/rules-of-hooks, $schema, App(), AddProductModal(), ConversationView() (+7 more)

### Community 15 - "Community 15"
Cohesion: 0.11
Nodes (11): Conversation, Return 'en' or 'ur'. Defaults to 'en'., Update session language preference.          Only updates when the message is cl, Get clarification candidate IDs as a list., Set clarification candidate IDs from a list., Get collected preferences as a dictionary., Set preferences dictionary., Get recently shown product IDs. (+3 more)

### Community 16 - "Community 16"
Cohesion: 0.14
Nodes (12): Message, Conversation and Message models., Customer, ConversationManager, DuplicateMessageError, AsyncSession, Conversation manager — manages conversation state and follow-up resolution.  Han, Manage conversation state for follow-up resolution. (+4 more)

### Community 17 - "Community 17"
Cohesion: 0.16
Nodes (11): AIRequestContext, OpenRouterProvider, OpenRouter-compatible AI provider.      Calls OpenRouter API with structured JSO, Call OpenRouter API with structured JSON output., Context sent to the AI provider for response generation., Safe fallback when AI fails — trigger human handoff., OpenRouter returns valid JSON — should parse correctly., No API key — should fall back safely. (+3 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (12): CatalogSearchResult, CatalogSearchService, MatchedProduct, Catalog search service — product matching within a single store.  Matching strat, Try exact SKU match on products and their variants., Score all products against query using alias, token, and fuzzy matching., A product match result with score and variant info., Filter matched variants by color and size. (+4 more)

### Community 19 - "Community 19"
Cohesion: 0.12
Nodes (13): OrderManager, Manage order state machine and order creation., conversation(), manager(), product(), Tests for order workflow state machine., Test order summary generation., Test order creation from conversation state. (+5 more)

### Community 20 - "Community 20"
Cohesion: 0.10
Nodes (19): express, @google/genai, qrcode, dependencies, axios, express, @google/genai, qrcode (+11 more)

### Community 21 - "Community 21"
Cohesion: 0.16
Nodes (18): axios, config, { createLogger, format, transports }, detectMessageType(), extractTextContent(), forwardAndReply(), gatewayStartedAtSeconds, getSkipReason() (+10 more)

### Community 22 - "Community 22"
Cohesion: 0.15
Nodes (11): get_db(), get_db_engine(), get_db_session_factory(), get_engine(), get_session_factory(), AsyncSession, Database connection and session management., Create async engine. Accepts override URL for testing. (+3 more)

### Community 23 - "Community 23"
Cohesion: 0.18
Nodes (7): LangChainProvider, OpenAIProvider, LangChain provider using LCEL and Pydantic structured output.      Every inbound, Map store/session language code to a human-readable name for the prompt., Backward-compatible provider name; implementation is LangChain-based., Test LangChain chains without making external API calls., TestLangChainProvider

### Community 24 - "Community 24"
Cohesion: 0.38
Nodes (16): async_client(), AsyncClient, AsyncSession, setup_test_data(), test_ai_provided_image_url_ignored(), test_ambiguous_reference_asks_for_clarification(), test_cross_store_rejected(), test_explicit_purchase_enters_order_workflow() (+8 more)

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (11): StorePolicy, MessageProcessor, Message processor — orchestrates the full deterministic pipeline.  Flow: normali, Orchestrate the full message processing pipeline., PolicyMatcher, PolicyMatchResult, Policy matching service — lookup store policies by type., Match incoming requests to store policies. (+3 more)

### Community 26 - "Community 26"
Cohesion: 0.13
Nodes (8): conversation_with_clarification(), conversation_with_product(), manager(), Tests for conversation memory and follow-up resolution., Conversation where customer asked about a black kurta., Conversation where customer was presented numbered choices., Test numbered choice disambiguation., TestClarificationResolution

### Community 27 - "Community 27"
Cohesion: 0.13
Nodes (5): api, axios, config, { createLogger, format, transports }, logger

### Community 28 - "Community 28"
Cohesion: 0.14
Nodes (7): client(), Tests for the demo API endpoint using FastAPI TestClient., Create async test client., TestHealthEndpoint, TestHumanHandoff, TestProductsEndpoint, TestStoresEndpoint

### Community 29 - "Community 29"
Cohesion: 0.26
Nodes (13): create_tables(), drop_tables(), init_db(), Initialize database engine and session factory., Create all tables (for dev/testing). Use Alembic in production., Drop all tables (for testing only)., db_engine(), Create test database engine. (+5 more)

### Community 30 - "Community 30"
Cohesion: 0.15
Nodes (7): Woh black wala medium mein kitne ka hai?, Test the exact inputs from the spec., Sky blue kurta medium size mein available hai? Price bhi bata dein., Navy blue sneakers size 42 ki price?, I want 2 pieces in size 40., COD hai aur delivery kitne din mein hogi?, TestSpecInputs

### Community 31 - "Community 31"
Cohesion: 0.17
Nodes (11): db_session(), event_loop(), make_fashion_products(), make_shoe_store(), Test fixtures for the backend test suite., Create event loop for async tests., Create a fresh DB session for each test., Create shoe store object (no DB). (+3 more)

### Community 32 - "Community 32"
Cohesion: 0.18
Nodes (9): config, { createLogger, format, transports }, { GoogleGenAI }, logger, transcribeAudio(), assert, { describe, it, mock, beforeEach, afterEach }, generateContentMock (+1 more)

### Community 33 - "Community 33"
Cohesion: 0.20
Nodes (7): ABC, AIProvider, AI provider abstraction for deterministic, LangChain, and OpenRouter flows.  Usa, Return provider name., Return whether this provider can make external model calls., Abstract base class for AI providers., Process a message context and return structured response.

### Community 34 - "Community 34"
Cohesion: 0.18
Nodes (6): AIEntitiesSchema, AIIntentSchema, BaseModel, Classify user intent and extract product query., Call OpenRouter API for intent classification., Expected structured output from the LLM for intent classification.

### Community 35 - "Community 35"
Cohesion: 0.24
Nodes (3): AsyncSession, TestProductsAPI, valid_store()

### Community 36 - "Community 36"
Cohesion: 0.20
Nodes (7): MockAIProvider, Mock AI provider for local dev and tests.      Returns structured responses usin, Mock processing — format response from candidates., empty_context(), mock_provider(), Tests for AI provider abstraction., sample_context()

### Community 37 - "Community 37"
Cohesion: 0.38
Nodes (10): Backend Service (FastAPI), Docker Compose Configuration, AI Pipeline Documentation, System Architecture, WhatsApp Gateway Documentation, Evolution API Service, Gateway Service (Node.js), PostgreSQL Database (+2 more)

### Community 38 - "Community 38"
Cohesion: 0.20
Nodes (6): Test follow-up message resolution from context., Medium ki price?' should resolve to the current product (black kurta)., If message has a new product query, don't use context., Follow-up with just size should fill color from context., Follow-up with explicit color should use the new color, not context., TestFollowupResolution

### Community 39 - "Community 39"
Cohesion: 0.20
Nodes (3): Test order state machine transitions., Test complete order flow from BROWSING to PAYMENT_METHOD_REQUIRED., TestStageAdvancement

### Community 40 - "Community 40"
Cohesion: 0.33
Nodes (6): get_ai_provider(), Get AI provider instance based on env config., Reset provider singleton (for testing)., reset_ai_provider(), Test provider factory., TestProviderFactory

### Community 41 - "Community 41"
Cohesion: 0.22
Nodes (6): make_fashion_policies(), Create fashion store policies., fashion_policies(), processor(), End-to-end tests for the message processor pipeline.  Tests the full flow: norma, TestEmptyAndEdge

### Community 42 - "Community 42"
Cohesion: 0.22
Nodes (7): config, app, config, { createLogger, format, transports }, createRoutes, express, logger

### Community 43 - "Community 43"
Cohesion: 0.22
Nodes (4): assert, { mock }, NOW, test

### Community 44 - "Community 44"
Cohesion: 0.29
Nodes (3): AIResponseSchema, Expected structured output from the AI provider., TestMockProvider

### Community 45 - "Community 45"
Cohesion: 0.25
Nodes (7): conversation_manager(), sample_products(), test_apply_context_stores_recently_shown(), test_catalog_search_ambiguous_still_works(), test_catalog_search_prioritizes_recently_shown(), test_recently_shown_products_limit(), test_resolve_followup_returns_recently_shown_and_preferences()

### Community 46 - "Community 46"
Cohesion: 0.32
Nodes (7): config, createRoutes(), evolutionClient, express, { webhookHandler, getCachedQR, mapConnectionState }, getCachedQR(), mapConnectionState()

### Community 47 - "Community 47"
Cohesion: 0.32
Nodes (7): ALLOWED_MIME_TYPES, analyzeImage(), config, { createLogger, format, transports }, { GoogleGenAI }, logger, sizeOf

### Community 48 - "Community 48"
Cohesion: 0.48
Nodes (7): extractStoreId(), handleConnectionUpdate(), handleMessagesUpsert(), handleQRCodeUpdated(), reportStatus(), validateWebhook(), webhookHandler()

### Community 49 - "Community 49"
Cohesion: 0.47
Nodes (5): evaluate(), load_cases(), main(), Path, Evaluate anonymized JSONL conversations against a running backend.  Usage:   pyt

### Community 51 - "Community 51"
Cohesion: 0.33
Nodes (4): Test that messages are processed only against the correct store's data., Searching for kurta in shoe store should not find anything., Searching for sneakers in fashion store should not find anything., TestStoreIsolation

### Community 52 - "Community 52"
Cohesion: 0.40
Nodes (3): lifespan(), FastAPI application entry point., Application lifespan: init DB on startup.

### Community 54 - "Community 54"
Cohesion: 0.40
Nodes (3): assert, { mock }, test

### Community 55 - "Community 55"
Cohesion: 0.50
Nodes (3): Seed demo stores, products, variants, aliases, and policies.  Two stores: 1. dem, Seed demo data into the database., seed()

### Community 57 - "Community 57"
Cohesion: 0.50
Nodes (4): make_shoe_products(), Create shoe products (no DB)., shoe_products(), shoe_products()

### Community 60 - "Community 60"
Cohesion: 0.67
Nodes (3): Always Active Skills, Caveman Skill, Graphify Skill

### Community 61 - "Community 61"
Cohesion: 0.67
Nodes (3): make_shoe_policies(), Create shoe store policies., shoe_policies()

## Knowledge Gaps
- **104 isolated node(s):** `$schema`, `oxc`, `react/rules-of-hooks`, `warn`, `name` (+99 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **22 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Product` connect `Community 4` to `Community 1`, `Community 35`, `Community 6`, `Community 7`, `Community 39`, `Community 9`, `Community 10`, `Community 45`, `Community 18`, `Community 19`, `Community 24`, `Community 25`, `Community 57`, `Community 31`?**
  _High betweenness centrality (0.156) - this node is a cross-community bridge._
- **Why does `Conversation` connect `Community 15` to `Community 0`, `Community 3`, `Community 4`, `Community 38`, `Community 39`, `Community 8`, `Community 10`, `Community 45`, `Community 16`, `Community 50`, `Community 19`, `Community 56`, `Community 24`, `Community 26`?**
  _High betweenness centrality (0.155) - this node is a cross-community bridge._
- **Why does `CatalogSearchService` connect `Community 18` to `Community 25`, `Community 2`, `Community 4`, `Community 45`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Are the 44 inferred relationships involving `Conversation` (e.g. with `Base` and `Customer`) actually correct?**
  _`Conversation` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 40 inferred relationships involving `Product` (e.g. with `Base` and `Store`) actually correct?**
  _`Product` has 40 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `ProcessedResponse` (e.g. with `ConversationController` and `ConversationManager`) actually correct?**
  _`ProcessedResponse` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `t()` (e.g. with `._fallback_response()` and `.process()`) actually correct?**
  _`t()` has 34 INFERRED edges - model-reasoned connections that need verification._