"""Catalogue freshness + order-item exposure.

Two guarantees the seller depends on:
1. When the seller edits the catalogue (price/stock/new product/deactivate),
   the very next customer reply reflects the change — no stale cache.
2. Orders expose exactly which products were ordered via GET /orders.

Uses an isolated in-memory engine + get_db override (like test_image_flow) so
committed rows never leak into the shared conftest engine.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.product import Product, ProductVariant
from app.models.order import Order, OrderItem

pytestmark = pytest.mark.asyncio

TOKEN = {"X-Internal-Token": "dev-internal-token"}


@pytest_asyncio.fixture(scope="module")
async def iso_db():
    engine = get_engine("sqlite+aiosqlite:///:memory:")
    factory = get_session_factory(engine)
    await create_tables(engine)
    yield engine, factory
    await drop_tables(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(iso_db):
    _, factory = iso_db
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


async def _msg(client, store_id, text, customer="923001110000"):
    r = await client.post(
        "/internal/whatsapp/messages",
        json={"store_id": store_id, "customer_number": customer, "message": text},
        headers=TOKEN,
    )
    assert r.status_code == 200
    return r.json()


async def test_price_update_reflected_in_next_reply(async_client, db_session):
    store = Store(business_name="Fresh Store", owner_name="Owner", preferred_language="english")
    db_session.add(store)
    await db_session.flush()
    p = Product(store_id=store.id, name="Denim Jacket", sku="DJ01", base_price=1000, is_active=True)
    db_session.add(p)
    await db_session.flush()
    v = ProductVariant(product_id=p.id, color="Blue", size="M", price=1000, stock=5, is_active=True)
    db_session.add(v)
    await db_session.flush()

    first = await _msg(async_client, store.id, "show me Denim Jacket", customer="923001110001")
    assert "Price: Rs. 1,000" in first["message"]

    # Seller raises the price.
    v.price = 1500
    await db_session.flush()

    second = await _msg(async_client, store.id, "show me Denim Jacket", customer="923001110002")
    assert "Price: Rs. 1,500" in second["message"]
    assert "Price: Rs. 1,000" not in second["message"]


async def test_new_product_is_immediately_searchable(async_client, db_session):
    store = Store(business_name="Grow Store", owner_name="Owner", preferred_language="english")
    db_session.add(store)
    await db_session.flush()
    p = Product(store_id=store.id, name="Cotton Shirt", sku="CS01", base_price=800, is_active=True)
    db_session.add(p)
    await db_session.flush()
    db_session.add(ProductVariant(product_id=p.id, color="White", size="M", price=800, stock=5, is_active=True))
    await db_session.flush()

    before = await _msg(async_client, store.id, "show me Leather Belt", customer="923001110003")
    assert before["matched_product_id"] is None

    # Seller adds it.
    p2 = Product(store_id=store.id, name="Leather Belt", sku="LB01", base_price=600, is_active=True)
    db_session.add(p2)
    await db_session.flush()
    db_session.add(ProductVariant(product_id=p2.id, color="Brown", size="L", price=600, stock=9, is_active=True))
    await db_session.flush()

    after = await _msg(async_client, store.id, "show me Leather Belt", customer="923001110004")
    assert after["matched_product_id"] == p2.id


async def test_deactivated_product_no_longer_offered(async_client, db_session):
    store = Store(business_name="Trim Store", owner_name="Owner", preferred_language="english")
    db_session.add(store)
    await db_session.flush()
    p = Product(store_id=store.id, name="Silk Scarf", sku="SS01", base_price=1200, is_active=True)
    db_session.add(p)
    await db_session.flush()
    db_session.add(ProductVariant(product_id=p.id, color="Red", size="M", price=1200, stock=4, is_active=True))
    await db_session.flush()

    before = await _msg(async_client, store.id, "show me Silk Scarf", customer="923001110005")
    assert before["matched_product_id"] == p.id

    # Seller deactivates it.
    p.is_active = False
    await db_session.flush()

    after = await _msg(async_client, store.id, "show me Silk Scarf", customer="923001110006")
    assert after["matched_product_id"] is None


async def test_orders_endpoint_exposes_line_items(async_client, db_session):
    store = Store(business_name="Order Store", owner_name="Owner", preferred_language="english")
    db_session.add(store)
    await db_session.flush()

    order = Order(
        store_id=store.id, conversation_id="conv-x", customer_id="cust-x",
        status="pending", total_amount=3000.0,
        customer_name="Sara", customer_phone="923005556677",
        customer_address="42 Mall Road", customer_city="Karachi",
        payment_method="COD",
    )
    order.items = [
        OrderItem(
            product_id="prod-x", variant_id="var-x", product_name="Party Dress",
            variant_description="Black M", quantity=2, unit_price=1500.0,
        )
    ]
    db_session.add(order)
    await db_session.flush()

    r = await async_client.get(f"/api/stores/{store.id}/orders")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    o = data[0]
    assert o["customer_city"] == "Karachi"
    assert o["customer_address"] == "42 Mall Road"
    assert len(o["items"]) == 1
    item = o["items"][0]
    assert item["product_id"] == "prod-x"
    assert item["variant_id"] == "var-x"
    assert item["product_name"] == "Party Dress"
    assert item["quantity"] == 2
    assert item["unit_price"] == 1500.0
    assert item["line_total"] == 3000.0
