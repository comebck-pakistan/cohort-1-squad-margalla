import asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import get_db
from app.models.product import Product, ProductVariant
from app.models.store import Store
import uuid
from unittest.mock import patch
from app.services.ai_provider import AIResponseSchema

async def run():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            store_id = f"test-store-{uuid.uuid4().hex[:8]}"
            store = Store(id=store_id, business_name="Test Store", owner_name="Owner", ai_enabled=True)
            session.add(store)
            await session.commit()
            p1 = Product(store_id=store.id, name="Blue Kurta", base_price=10.0, is_active=True, sku="SKU1", image_url="/uploads/blue.jpg")
            session.add(p1)
            await session.flush()
            v1 = ProductVariant(product_id=p1.id, price=10.0, stock=5, size="M")
            session.add(v1)
            await session.commit()
            
            async def mock_process(*args, **kwargs):
                return AIResponseSchema(
                    response_message="I think the price is Rs. 9999 and we have 100 in stock.",
                    selected_product_id=p1.id
                )
            
            with patch("app.services.ai_provider.MockAIProvider.process", side_effect=mock_process):
                res = await ac.post("/internal/whatsapp/messages", json={
                    "store_id": store.id,
                    "customer_number": "923000000001",
                    "message": "blue kurta price?",
                }, headers={"X-Internal-Token": "dev-internal-token"})
                print(res.status_code)
                print(res.json())

if __name__ == "__main__":
    asyncio.run(run())
