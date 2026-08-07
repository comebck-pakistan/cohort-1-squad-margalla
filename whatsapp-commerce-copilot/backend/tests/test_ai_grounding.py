"""Tests for LLM catalog grounding and intent/query orchestration.

Each test validates a specific grounding requirement:
1. Hallucinated product IDs rejected
2. Hallucinated variant IDs rejected
3. Hallucinated price/stock/image ignored — authoritative values rendered
4. Low-confidence LLM classification doesn't override deterministic
5. Valid query rewriting accepted
6. No candidates → clear not-found message
7. Database failure → service error, not fabrication
8. AI timeout → deterministic fallback
9. Malformed structured output → graceful fallback
10. Provider unavailable → deterministic path
11. Newly created product found immediately
12. Cross-store and inactive products rejected
"""
import asyncio
import pytest
import pytest_asyncio
import uuid
from unittest.mock import patch

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.store import Store
from app.models.product import Product, ProductVariant
from app.database import get_db, init_db, create_tables, drop_tables
from app.services.ai_provider import AIResponseSchema, AIIntentSchema, AIIntentEnum

pytestmark = pytest.mark.asyncio


# ---- Fixtures ----

@pytest_asyncio.fixture(scope="module")
async def db_engine():
    engine, factory = init_db("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    yield engine, factory
    await drop_tables(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    engine, factory = db_engine
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def store(db_session):
    store_id = f"test-store-{uuid.uuid4().hex[:8]}"
    store = Store(id=store_id, business_name="Test Store", owner_name="Owner", ai_enabled=True)
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)
    return store


@pytest_asyncio.fixture
async def products(db_session, store):
    p1 = Product(
        store_id=store.id, name="Blue Kurta", base_price=10.0,
        is_active=True, sku="SKU1", image_url="/uploads/blue.jpg",
    )
    p2 = Product(
        store_id=store.id, name="Red Kurta", base_price=20.0,
        is_active=True, sku="SKU2",
    )
    db_session.add_all([p1, p2])
    await db_session.flush()
    v1 = ProductVariant(product_id=p1.id, price=10.0, stock=5, size="M")
    v2 = ProductVariant(product_id=p2.id, price=20.0, stock=5, size="L")
    db_session.add_all([v1, v2])
    await db_session.commit()
    await db_session.refresh(p1)
    await db_session.refresh(p2)
    return [p1, p2]


@pytest_asyncio.fixture
async def async_client(db_session, store):
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _post(async_client, store_id, message, customer="923000000001"):
    """Helper: send message through internal endpoint."""
    return async_client.post(
        "/internal/whatsapp/messages",
        json={
            "store_id": store_id,
            "customer_number": customer,
            "message": message,
        },
        headers={"X-Internal-Token": "dev-internal-token"},
    )


# ---- Test 1: Hallucinated product ID ----

@pytest.mark.asyncio
async def test_hallucinated_product_id(async_client, store, products):
    """AI returns a product ID not in the candidate set → must be rejected."""
    async def mock_process(*a, **kw):
        return AIResponseSchema(
            response_message="Here it is",
            selected_product_id="fake-id-does-not-exist",
        )

    with patch("app.services.ai_provider.MockAIProvider.process", side_effect=mock_process):
        res = await _post(async_client, store.id, "show me kurta")
        data = res.json()
        assert data["matched_product_id"] != "fake-id-does-not-exist"
        assert "fake-id" not in data.get("message", "")


# ---- Test 2: Hallucinated variant ID ----

@pytest.mark.asyncio
async def test_hallucinated_variant_id(async_client, store, products):
    """AI returns a variant ID not in the candidate variants → must be dropped."""
    p1 = products[0]

    async def mock_process(*a, **kw):
        return AIResponseSchema(
            response_message="Here it is",
            selected_product_id=p1.id,
            selected_variant_id="fake-var-id",
        )

    with patch("app.services.ai_provider.MockAIProvider.process", side_effect=mock_process):
        res = await _post(async_client, store.id, "show me blue kurta")
        assert res.json()["matched_variant_id"] != "fake-var-id"


# ---- Test 3: Hallucinated image/price/stock ----

@pytest.mark.asyncio
async def test_hallucinated_price_stock_image(async_client, store, products):
    """AI claims Rs. 9999 but authoritative price is Rs. 10 → authoritative wins."""
    p1 = products[0]

    async def mock_process(*a, **kw):
        return AIResponseSchema(
            response_message="I think the price is Rs. 9999.",
            selected_product_id=p1.id,
        )

    with patch("app.services.ai_provider.MockAIProvider.process", side_effect=mock_process):
        res = await _post(async_client, store.id, "blue kurta")
        msg = res.json()["message"]
        # Authoritative price must appear
        assert "Rs. 10" in msg


# ---- Test 4: Low-confidence LLM override rejected ----

@pytest.mark.asyncio
async def test_low_confidence_llm_override_rejected(async_client, store, products):
    """LLM classifies as order_request with 0.1 confidence → deterministic wins."""
    async def mock_classify(*a, **kw):
        return AIIntentSchema(intent=AIIntentEnum.ORDER_REQUEST, confidence=0.1)

    with patch("app.services.ai_provider.MockAIProvider.classify_intent", side_effect=mock_classify):
        res = await _post(async_client, store.id, "show me blue kurta")
        assert res.json()["intent"] == "product_search"


# ---- Test 5: Valid query rewriting ----

@pytest.mark.asyncio
async def test_valid_query_rewriting(async_client, store, products):
    """LLM rewrites 'lal wala' → 'Red Kurta' → correct product matched."""
    p2 = products[1]

    async def mock_classify(*a, **kw):
        return AIIntentSchema(
            intent=AIIntentEnum.PRODUCT_SEARCH,
            confidence=0.9,
            product_query="Red Kurta",
        )

    with patch("app.services.ai_provider.MockAIProvider.classify_intent", side_effect=mock_classify):
        res = await _post(async_client, store.id, "lal wala", customer="923000000005")
        data = res.json()
        assert data["matched_product_id"] == p2.id


# ---- Test 6: No candidates ----

@pytest.mark.asyncio
async def test_no_candidates(async_client, store, products):
    """Query for nonexistent product → clear not-found message."""
    res = await _post(async_client, store.id, "show me a purple jacket", customer="923000000006")
    data = res.json()
    assert data["matched_product_id"] is None
    msg_lower = data["message"].lower()
    assert any(w in msg_lower for w in ("not", "product", "sorry", "nahi"))


# ---- Test 7: Database failure ----

@pytest.mark.asyncio
async def test_database_failure(async_client, store, products):
    """DB error during processing → service error response, not fabrication."""
    with patch(
        "app.services.catalog_search.CatalogSearchService.search",
        side_effect=Exception("DB Error"),
    ):
        res = await _post(async_client, store.id, "blue kurta", customer="923000000007")
        # Should get a 200 with service error, not a crash
        assert res.status_code == 200
        data = res.json()
        # Must not contain fabricated product data
        assert data.get("matched_product_id") is None


# ---- Test 8: AI timeout ----

@pytest.mark.asyncio
async def test_ai_timeout(async_client, store, products):
    """AI provider times out → deterministic fallback still returns correct product."""
    p1 = products[0]

    async def mock_timeout(*a, **kw):
        raise asyncio.TimeoutError()

    with patch("app.services.ai_provider.MockAIProvider.process", side_effect=mock_timeout):
        res = await _post(async_client, store.id, "blue kurta", customer="923000000008")
        assert res.status_code == 200
        assert res.json()["matched_product_id"] == p1.id


# ---- Test 9: Malformed structured output ----

@pytest.mark.asyncio
async def test_malformed_structured_output(async_client, store, products):
    """AI returns unparseable output → graceful fallback, no crash."""
    from pydantic import ValidationError

    async def mock_malformed(*a, **kw):
        raise ValidationError([], model=AIResponseSchema)

    with patch("app.services.ai_provider.MockAIProvider.process", side_effect=mock_malformed):
        res = await _post(async_client, store.id, "blue kurta", customer="923000000009")
        assert res.status_code == 200


# ---- Test 10: Provider unavailable ----

@pytest.mark.asyncio
async def test_provider_unavailable(async_client, store, products):
    """AI provider not configured → deterministic pipeline works alone."""
    with patch("app.services.ai_provider.MockAIProvider.is_configured", return_value=False):
        res = await _post(async_client, store.id, "blue kurta", customer="923000000010")
        assert res.status_code == 200
        # Should still find the product via deterministic path
        assert res.json()["matched_product_id"] is not None


# ---- Test 11: Newly created product ----

@pytest.mark.asyncio
async def test_newly_created_product(async_client, store, products, db_session):
    """A product added after startup is found immediately from DB."""
    p_new = Product(store_id=store.id, name="Green Hat", base_price=15.0, is_active=True)
    db_session.add(p_new)
    await db_session.flush()
    v_new = ProductVariant(product_id=p_new.id, price=15.0, stock=10)
    db_session.add(v_new)
    await db_session.commit()

    res = await _post(async_client, store.id, "show me green hat")
    assert res.json()["matched_product_id"] == p_new.id


# ---- Test 12: Cross-store and inactive products rejected ----

@pytest.mark.asyncio
async def test_cross_store_and_inactive_rejected(async_client, store, products, db_session):
    """Products from another store or inactive in this store must never appear."""
    store2 = Store(id=f"store2-{uuid.uuid4().hex[:8]}", business_name="S2", owner_name="O2")
    db_session.add(store2)
    # Cross-store product
    p_cross = Product(store_id=store2.id, name="Yellow Jacket", base_price=50.0, is_active=True)
    # Inactive product in our store
    p_inactive = Product(store_id=store.id, name="Inactive Jacket", base_price=50.0, is_active=False)
    db_session.add_all([p_cross, p_inactive])
    await db_session.commit()

    res = await _post(async_client, store.id, "show me jacket")
    data = res.json()
    # Must not match cross-store or inactive products
    if data["matched_product_id"]:
        assert data["matched_product_id"] != p_cross.id
        assert data["matched_product_id"] != p_inactive.id
