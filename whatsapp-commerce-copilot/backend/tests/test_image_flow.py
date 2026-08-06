import pytest
import uuid
import io
import os
from PIL import Image
from httpx import AsyncClient
from app.models.product import Product
from app.schemas.api import InternalSessionEvent
from app.services.ai_provider import AIRequestContext, AIResponseSchema
from sqlalchemy import select

from app.models.store import Store
from app.database import get_db, init_db, create_tables, drop_tables
import pytest_asyncio
from httpx import ASGITransport
from app.main import app

pytestmark = pytest.mark.asyncio

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
async def async_client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def store(db_session):
    import uuid
    store_id = f"test-store-{uuid.uuid4().hex[:8]}"
    store = Store(id=store_id, business_name="Test Store", owner_name="Owner", ai_enabled=True)
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)
    return store

@pytest.mark.asyncio
async def test_image_upload_validation_and_conversion(async_client, store):
    # Create a small valid JPEG in memory
    img = Image.new('RGB', (100, 100), color='red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)

    data = {
        "name": "Test Image Product",
        "price": 1000.0,
        "stock": 10
    }
    files = {
        "image": ("test.jpg", img_byte_arr, "image/jpeg")
    }

    # Upload via products router
    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data,
        files=files
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["image_url"] is not None
    assert res_data["image_url"].endswith(".jpg")

    # Verify the file was saved
    filename = res_data["image_url"].split("/")[-1]
    filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads", filename))
    assert os.path.exists(filepath)
    
    # Read saved file to ensure it's a valid JPEG
    saved_img = Image.open(filepath)
    assert saved_img.format == "JPEG"

@pytest.mark.asyncio
async def test_invalid_image_upload_rejected(async_client, store):
    data = {
        "name": "Invalid Image Product",
        "price": 1000.0,
        "stock": 10
    }
    # Send a text file disguised as an image
    files = {
        "image": ("test.jpg", b"this is not an image", "image/jpeg")
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data,
        files=files
    )

    assert response.status_code == 400
    assert "Unsupported image format or corrupted file" in response.json()["detail"]

@pytest.mark.asyncio
async def test_large_image_upload_rejected(async_client, store):
    data = {
        "name": "Large Image Product",
        "price": 1000.0,
        "stock": 10
    }
    # Create a dummy payload larger than 5MB
    large_payload = b"0" * (5 * 1024 * 1024 + 10)
    files = {
        "image": ("test.jpg", large_payload, "image/jpeg")
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data,
        files=files
    )

    assert response.status_code == 400
    assert "Image size exceeds 5MB limit" in response.json()["detail"]

@pytest.mark.asyncio
async def test_product_creation_without_image(async_client, store):
    data = {
        "name": "No Image Product",
        "price": 500.0,
        "stock": 10
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["image_url"] is None

@pytest.mark.asyncio
async def test_ai_promise_rejected(db_session, store):
    """Test that if the AI promises to fetch a picture, the controller falls back to the deterministic response."""
    from app.services.conversation_controller import ConversationController
    from app.services.response_builder import ProcessedResponse
    from app.models.conversation import Conversation
    from app.services.ai_provider import MockAIProvider
    
    # We patch MockAIProvider to return a promise
    class NaughtyAIProvider(MockAIProvider):
        async def process(self, context):
            return AIResponseSchema(
                response_message="Please hold on while I fetch the pictures for you.",
                confidence=0.8,
            )
            
    import app.services.conversation_controller as cc
    original_provider = cc.get_ai_provider
    cc.get_ai_provider = lambda: NaughtyAIProvider()
    
    try:
        controller = ConversationController()
        conv = Conversation(store_id=store.id, customer_phone="923000000000", customer_id="cust_123")
        db_session.add(conv)
        await db_session.commit()
        
        initial_response = ProcessedResponse(
            message="Deterministic product details here.",
            intent="picture_request",
            confidence=0.3, # low confidence to trigger AI
            needs_clarification=True
        )
        
        final_response = await controller._optional_ai_response(
            conv, "show me its picture", initial_response, [], [], store.business_name, "en"
        )
        
        # Should fallback to the original deterministic response because the AI promised to fetch
        assert final_response.message == "Deterministic product details here."
    finally:
        cc.get_ai_provider = original_provider

@pytest.mark.asyncio
async def test_missing_image_returns_honest_message(async_client, store, db_session):
    from app.models.product import Product, ProductVariant
    from app.config import get_settings
    settings = get_settings()
    
    # Create product without image
    p = Product(store_id=store.id, name="No Image Shirt", base_price=500.0)
    db_session.add(p)
    await db_session.flush()
    db_session.add(ProductVariant(product_id=p.id, price=500.0, stock=10))
    await db_session.commit()
    
    # Simulate internal processing of a picture request
    response = await async_client.post(
        "/internal/whatsapp/messages",
        json={
            "store_id": store.id,
            "customer_number": "923001234567",
            "message": "show me picture of No Image Shirt",
            "message_type": "text"
        },
        headers={"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert "A picture for this product has not been uploaded yet" in res_data["message"] or "picture abhi catalog mein upload nahi hai" in res_data["message"]
    assert res_data["image_url"] is None
