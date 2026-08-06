import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.main import app
from app.models.conversation import Conversation
from app.models.product import Product, ProductVariant
from app.models.store import Store
import pytest_asyncio
from app.routers.internal import _verify_internal_token

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

pytestmark = pytest.mark.asyncio

async def setup_test_data(db: AsyncSession):
    store = Store(business_name="Test Store", owner_name="Owner")
    db.add(store)
    await db.flush()

    p1 = Product(store_id=store.id, name="Blue Kurta", sku="BK01", base_price=1000, image_url="/uploads/blue.jpg", is_active=True)
    p2 = Product(store_id=store.id, name="Red Kurta", sku="RK01", base_price=1200, image_url="/uploads/red.jpg", is_active=True)
    p3 = Product(store_id=store.id, name="Green Shirt", sku="GS01", base_price=800, image_url=None, is_active=True)
    p4 = Product(store_id=store.id, name="Inactive Item", sku="IN01", base_price=500, image_url="/uploads/in.jpg", is_active=False)
    
    other_store = Store(business_name="Other Store", owner_name="Other")
    db.add(other_store)
    await db.flush()
    p5 = Product(store_id=other_store.id, name="Other Store Item", sku="OS01", base_price=100, image_url="/uploads/os.jpg", is_active=True)
    
    db.add_all([p1, p2, p3, p4, p5])
    await db.flush()

    v1 = ProductVariant(product_id=p1.id, color="Blue", size="M", price=1000, stock=5)
    v2 = ProductVariant(product_id=p2.id, color="Red", size="L", price=1200, stock=2)
    v3 = ProductVariant(product_id=p3.id, color="Green", size="S", price=800, stock=10)
    db.add_all([v1, v2, v3])
    await db.commit()

    return store, p1, p2, p3, p4, p5


async def test_single_matched_product_selected(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, *_ = await setup_test_data(db_session)
    
    # Send message referencing "Blue Kurta"
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Show me the Blue Kurta",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["matched_product_id"] == p1.id
    assert data["image_url"] == "/uploads/blue.jpg"
    assert "Blue Kurta" in data["message"]
    assert "Price: Rs. 1,000" in data["message"]
    assert "Stock: Available" in data["message"]

    # Verify context persistence
    result = await db_session.execute(select(Conversation).where(Conversation.store_id == store.id))
    conv = result.scalar_one()
    assert conv.current_product_id == p1.id
    assert conv.order_stage == "BROWSING"


async def test_two_product_shortlist_preserves_order(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, p2, *_ = await setup_test_data(db_session)
    
    # Ask for generic "Kurta" - should return multiple
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Show me kurtas",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    assert resp.status_code == 200
    data = resp.json()
    assert "1. Blue Kurta" in data["message"]
    assert "2. Red Kurta" in data["message"]
    assert data["needs_clarification"] is True

    # Verify context
    result = await db_session.execute(select(Conversation).where(Conversation.store_id == store.id))
    conv = result.scalar_one()
    assert conv.pending_clarification == "product_selection"
    candidates = conv.get_clarification_candidates_list()
    assert len(candidates) >= 2
    assert candidates[0] == p1.id
    assert candidates[1] == p2.id


async def test_number_2_selects_second_product(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, p2, *_ = await setup_test_data(db_session)
    
    # 1. Ask for generic "Kurta"
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Show me kurtas",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    # 2. Select number 2
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "number 2",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] == p2.id
    assert data["image_url"] == "/uploads/red.jpg"
    assert "Red Kurta" in data["message"]
    
    # Verify order not created
    result = await db_session.execute(select(Conversation).where(Conversation.store_id == store.id))
    conv = result.scalar_one()
    assert conv.order_stage == "BROWSING"


async def test_second_one_selects_second_product(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, p2, *_ = await setup_test_data(db_session)
    
    # 1. Ask for generic "Kurta"
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234568",
        "message": "Show me kurtas",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    # 2. Select "second one"
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234568",
        "message": "second one",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] == p2.id
    assert data["image_url"] == "/uploads/red.jpg"


async def test_that_one_resolves_when_one_candidate(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, *_ = await setup_test_data(db_session)
    
    # 1. Select a specific product
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Blue Kurta",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    # 2. Refer to it
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Yes, that one",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] == p1.id
    assert data["image_url"] == "/uploads/blue.jpg"
    
    # Should still not advance order since quantity/size not specified
    result = await db_session.execute(select(Conversation).where(Conversation.store_id == store.id))
    conv = result.scalar_one()
    assert conv.order_stage == "BROWSING"


async def test_ambiguous_reference_asks_for_clarification(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, p2, *_ = await setup_test_data(db_session)
    
    # 1. Search returns multiple
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "kurtas",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    # 2. Refer ambiguously
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "this one",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    # "this one" requires a single selected context, but we had multiple candidates.
    # Therefore it should fail or ask for clarification.
    assert data["matched_product_id"] is None
    assert data.get("needs_clarification", False) or data.get("intent") == "unknown"


async def test_send_picture_again(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, *_ = await setup_test_data(db_session)
    
    # 1. Select product
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Blue Kurta",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    # 2. Request picture
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Send the picture again",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] == p1.id
    assert data["image_url"] == "/uploads/blue.jpg"


async def test_price_follow_up(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, *_ = await setup_test_data(db_session)
    
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Blue Kurta",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "How much is it?",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] == p1.id
    assert "1,000" in data["message"]


async def test_ai_provided_image_url_ignored(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, p2, p3, *_ = await setup_test_data(db_session)
    
    # 1. Select p3
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Green Shirt",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    # 2. Ask for picture (p3 has no image)
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "photo of green shirt",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] == p3.id
    assert data["image_url"] is None
    assert "upload" in data["message"].lower() or "not" in data["message"].lower()


async def test_cross_store_rejected(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, p2, p3, p4, p5 = await setup_test_data(db_session)
    
    # Try to access p5 (from Other Store) while sending to "Store"
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Other Store Item",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] is None


async def test_inactive_product_rejected(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, p2, p3, p4, p5 = await setup_test_data(db_session)
    
    # Try to access p4 (inactive)
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234567",
        "message": "Inactive Item",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] is None


async def test_explicit_purchase_enters_order_workflow(async_client: AsyncClient, db_session: AsyncSession):
    store, p1, *_ = await setup_test_data(db_session)
    
    # Set context
    await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234569",
        "message": "Blue Kurta",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    # Explicit purchase intent
    resp = await async_client.post("/internal/whatsapp/messages", json={
        "store_id": store.id,
        "customer_number": "923001234569",
        "message": "I want to buy this, send me 2 of them",
    }, headers={"X-Internal-Token": "dev-internal-token"})
    
    data = resp.json()
    assert data["matched_product_id"] == p1.id
    
    # Should advance order
    result = await db_session.execute(select(Conversation).where(Conversation.store_id == store.id))
    conv = result.scalar_one()
    assert conv.order_stage in {"PRODUCT_SELECTED", "VARIANT_SELECTED", "QUANTITY_SELECTED", "CUSTOMER_DETAILS_REQUIRED"}
