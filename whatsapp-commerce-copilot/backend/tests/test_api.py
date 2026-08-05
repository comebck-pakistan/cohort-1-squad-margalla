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


class TestConversationAwareFlow:
    endpoint = "/internal/whatsapp/messages"
    headers = {"X-Internal-Token": "dev-internal-token"}

    @pytest.mark.asyncio
    async def test_multi_turn_product_reference_and_picture(self, client):
        customer = "923009990001"
        first = await client.post(self.endpoint, headers=self.headers, json={
            "store_id": "demo-store-fashion",
            "customer_number": customer,
            "message": "maroon kurta dikhao",
        })
        assert first.status_code == 200
        product_id = first.json()["matched_product_id"]
        assert product_id

        followup = await client.post(self.endpoint, headers=self.headers, json={
            "store_id": "demo-store-fashion",
            "customer_number": customer,
            "message": "medium?",
        })
        assert followup.status_code == 200
        assert followup.json()["matched_product_id"] == product_id
        assert followup.json()["extracted_entities"]["size"].lower() == "medium"

        picture = await client.post(self.endpoint, headers=self.headers, json={
            "store_id": "demo-store-fashion",
            "customer_number": customer,
            "message": "send pics",
        })
        assert picture.status_code == 200
        assert picture.json()["matched_product_id"] == product_id
        assert picture.json()["intent"] == "picture_request"

    @pytest.mark.asyncio
    async def test_unknown_and_link_are_not_catalogue_misses(self, client):
        for message in ("thanks", "https://meet.google.com/test"):
            response = await client.post(self.endpoint, headers=self.headers, json={
                "store_id": "demo-store-fashion",
                "customer_number": "923009990002",
                "message": message,
            })
            assert response.status_code == 200
            assert "catalog mein nahi mila" not in response.json()["message"]

    @pytest.mark.asyncio
    async def test_complete_order_and_idempotent_confirmation(self, client):
        customer = "923009990003"

        async def send(message, message_id):
            response = await client.post(self.endpoint, headers=self.headers, json={
                "store_id": "demo-store-fashion",
                "customer_number": customer,
                "message": message,
                "whatsapp_message_id": message_id,
            })
            assert response.status_code == 200
            return response.json()

        await send("sky blue kurta medium order kar do", "flow-1")
        quantity = await send("2 pieces", "flow-2")
        # Customer sent Roman Urdu → response is now Urdu-script.
        # Check that the message asks for name/phone in either language.
        qty_msg = quantity["message"]
        has_name_prompt = (
            "naam" in qty_msg.lower()
            or "name" in qty_msg.lower()
            or any(0x0600 <= ord(c) <= 0x06FF for c in qty_msg)  # contains Urdu script
        )
        assert has_name_prompt, f"Expected name/phone prompt, got: {qty_msg}"
        await send("Ali Hassan", "flow-3")
        await send("House 12, Block A, Lahore", "flow-4")
        summary = await send("COD", "flow-5")
        summ_msg = summary["message"]
        has_summary = (
            "order summary" in summ_msg.lower()
            or any(0x0600 <= ord(c) <= 0x06FF for c in summ_msg)  # Urdu script contains summary
        )
        assert has_summary, f"Expected order summary, got: {summ_msg}"
        confirmed = await send("haan confirm", "flow-6")
        conf_msg = confirmed["message"]
        # Both English and Urdu confirmations include the literal "ID:" string
        assert "ID:" in conf_msg, f"Expected order confirmation with ID, got: {conf_msg}"

        duplicate = await send("haan confirm", "flow-6")
        assert duplicate["message"] == confirmed["message"]

        orders = await client.get("/api/stores/demo-store-fashion/orders")
        matching = [
            order for order in orders.json()
            if order["customer_phone"] == customer
        ]
        assert len(matching) == 1
        assert matching[0]["total_amount"] == 5000
