import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.product import Product, ProductVariant

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def valid_store(db_session: AsyncSession):
    import uuid
    from app.models.store import Store
    store = Store(id=str(uuid.uuid4()), business_name="CRUD Store", owner_name="Owner", preferred_language="english")
    db_session.add(store)
    await db_session.commit()
    return store

class TestProductsAPI:
    @pytest.mark.asyncio
    async def test_create_product_legacy(self, client, valid_store, db_session: AsyncSession):
        res = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Legacy Product",
            "price": "500",
            "stock": "10",
        })
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Legacy Product"
        assert len(data["variants"]) == 1
        assert data["variants"][0]["price"] == 500
        assert data["variants"][0]["stock"] == 10

    @pytest.mark.asyncio
    async def test_create_product_with_variants(self, client, valid_store, db_session: AsyncSession):
        variants = [
            {"color": "Red", "size": "M", "price": 600, "stock": 5, "sku": "RED-M", "is_active": True},
            {"color": "Blue", "size": "L", "price": 650, "stock": 2, "sku": "BLU-L", "is_active": True}
        ]
        res = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Variant Product",
            "price": "600",
            "sku": "VAR-PROD",
            "variants": json.dumps(variants)
        })
        assert res.status_code == 200
        data = res.json()
        assert len(data["variants"]) == 2
        assert data["sku"] == "VAR-PROD"
        
        red_v = next(v for v in data["variants"] if v["color"] == "Red")
        assert red_v["sku"] == "RED-M"
        assert red_v["price"] == 600
        assert red_v["stock"] == 5

    @pytest.mark.asyncio
    async def test_create_product_duplicate_sku(self, client, valid_store, db_session: AsyncSession):
        variants = [
            {"price": 100, "stock": 1, "sku": "DUP-SKU"}
        ]
        res1 = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Prod 1",
            "price": "100",
            "variants": json.dumps(variants)
        })
        assert res1.status_code == 200

        res2 = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Prod 2",
            "price": "100",
            "sku": "DUP-SKU"
        })
        assert res2.status_code == 400
        assert "Duplicate store-level SKU" in res2.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_product_invalid_values(self, client, valid_store):
        res1 = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "   ",
            "price": "100",
        })
        assert res1.status_code == 400
        assert "Name cannot be empty" in res1.json()["detail"]

        res2 = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Neg Price",
            "price": "-10",
        })
        assert res2.status_code == 400
        assert "Price cannot be negative" in res2.json()["detail"]
        
        variants = [{"price": -5, "stock": 10}]
        res3 = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Neg Variant Price",
            "price": "10",
            "variants": json.dumps(variants)
        })
        assert res3.status_code == 400
        assert "Price cannot be negative" in res3.json()["detail"]

    @pytest.mark.asyncio
    async def test_variant_stock_update(self, client, valid_store):
        variants = [
            {"color": "Red", "price": 100, "stock": 5},
            {"color": "Blue", "price": 100, "stock": 2}
        ]
        res = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Stock Update Prod",
            "price": "100",
            "variants": json.dumps(variants)
        })
        assert res.status_code == 200
        data = res.json()
        red_v = next(v for v in data["variants"] if v["color"] == "Red")
        blue_v = next(v for v in data["variants"] if v["color"] == "Blue")

        # Update Red to 15
        patch_res = await client.patch(f"/api/stores/{valid_store.id}/products/{data['id']}/variants/{red_v['id']}/stock", json={
            "stock": 15
        })
        assert patch_res.status_code == 200
        assert patch_res.json()["stock"] == 15

        # Check list products
        list_res = await client.get(f"/api/stores/{valid_store.id}/products")
        prod = next(p for p in list_res.json() if p["id"] == data["id"])
        
        new_red_v = next(v for v in prod["variants"] if v["id"] == red_v["id"])
        new_blue_v = next(v for v in prod["variants"] if v["id"] == blue_v["id"])
        
        assert new_red_v["stock"] == 15
        assert new_blue_v["stock"] == 2 # Remains unchanged

    @pytest.mark.asyncio
    async def test_active_toggles(self, client, valid_store):
        variants = [
            {"color": "Red", "price": 100, "stock": 5, "is_active": True}
        ]
        res = await client.post(f"/api/stores/{valid_store.id}/products", data={
            "name": "Active Toggle Prod",
            "price": "100",
            "is_active": "true",
            "variants": json.dumps(variants)
        })
        assert res.status_code == 200
        data = res.json()
        assert data["is_active"] is True
        variant_id = data["variants"][0]["id"]
        product_id = data["id"]

        # Deactivate product
        res2 = await client.patch(f"/api/stores/{valid_store.id}/products/{product_id}/active", json={"is_active": False})
        assert res2.status_code == 200
        assert res2.json()["is_active"] is False

        # Deactivate variant
        res3 = await client.patch(f"/api/stores/{valid_store.id}/products/{product_id}/variants/{variant_id}/active", json={"is_active": False})
        assert res3.status_code == 200
        assert res3.json()["is_active"] is False

        # Verify via GET
        res4 = await client.get(f"/api/stores/{valid_store.id}/products")
        prod = next(p for p in res4.json() if p["id"] == product_id)
        assert prod["is_active"] is False
        assert prod["variants"][0]["is_active"] is False
