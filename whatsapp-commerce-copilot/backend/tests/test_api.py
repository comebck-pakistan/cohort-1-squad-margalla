"""Tests for the demo API endpoint using FastAPI TestClient."""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import init_db, create_tables, drop_tables


@pytest_asyncio.fixture(scope="module")
async def seed_and_start():
    """Initialize the app with test database and seed data."""
    engine, factory = init_db("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)

    # Seed test data
    from app.scripts.seed_demo import seed_demo
    async with factory() as session:
        await seed_demo(session)
        await session.commit()

    yield engine, factory

    await drop_tables(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(seed_and_start):
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health(self, client):
        r = await client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


class TestDemoEndpoint:
    @pytest.mark.asyncio
    async def test_sky_blue_kurta(self, client):
        r = await client.post("/api/demo/messages", json={
            "store_id": "demo-store-fashion",
            "customer_number": "923001234567",
            "message": "Sky blue kurta medium size mein available hai?",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["matched_product_id"] is not None
        assert len(data["sources"]) > 0
        assert data["store_id"] == "demo-store-fashion"

    @pytest.mark.asyncio
    async def test_nonexistent_store(self, client):
        r = await client.post("/api/demo/messages", json={
            "store_id": "nonexistent",
            "customer_number": "923001234567",
            "message": "hello",
        })
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_message(self, client):
        r = await client.post("/api/demo/messages", json={
            "store_id": "demo-store-fashion",
            "customer_number": "923001234567",
            "message": "",
        })
        assert r.status_code == 422


class TestStoresEndpoint:
    @pytest.mark.asyncio
    async def test_list_stores(self, client):
        r = await client.get("/api/stores")
        assert r.status_code == 200
        stores = r.json()
        assert len(stores) >= 2

    @pytest.mark.asyncio
    async def test_get_store(self, client):
        r = await client.get("/api/stores/demo-store-fashion")
        assert r.status_code == 200
        data = r.json()
        assert data["business_name"] == "Noor Fashion House"

    @pytest.mark.asyncio
    async def test_get_nonexistent_store(self, client):
        r = await client.get("/api/stores/nonexistent")
        assert r.status_code == 404


class TestProductsEndpoint:
    @pytest.mark.asyncio
    async def test_list_products(self, client):
        r = await client.get("/api/stores/demo-store-fashion/products")
        assert r.status_code == 200
        products = r.json()
        assert len(products) >= 1

class TestHumanHandoff:
    @pytest.mark.asyncio
    async def test_takeover_and_enable(self, client):
        # 1. Send a message to create a conversation
        r1 = await client.post("/api/demo/messages", json={
            "store_id": "demo-store-fashion",
            "customer_number": "923112223344",
            "message": "hello"
        })
        assert r1.status_code == 200

        # 2. Get the list of conversations for this store
        r2 = await client.get("/api/stores/demo-store-fashion/conversations")
        assert r2.status_code == 200
        convs = r2.json()
        assert len(convs) >= 1
        conv_id = convs[0]["id"]
        assert convs[0]["is_ai_controlled"] is True

        # 3. Takeover
        r3 = await client.post(f"/api/stores/demo-store-fashion/conversations/{conv_id}/takeover")
        assert r3.status_code == 200
        assert r3.json()["status"] == "human_control"

        # 4. Verify takeover
        r4 = await client.get(f"/api/stores/demo-store-fashion/conversations/{conv_id}")
        assert r4.status_code == 200
        assert r4.json()["is_ai_controlled"] is False

        # 5. Enable AI
        r5 = await client.post(f"/api/stores/demo-store-fashion/conversations/{conv_id}/enable-ai")
        assert r5.status_code == 200
        assert r5.json()["status"] == "ai_control"

        # 6. Verify enable AI
        r6 = await client.get(f"/api/stores/demo-store-fashion/conversations/{conv_id}")
        assert r6.status_code == 200
        assert r6.json()["is_ai_controlled"] is True
