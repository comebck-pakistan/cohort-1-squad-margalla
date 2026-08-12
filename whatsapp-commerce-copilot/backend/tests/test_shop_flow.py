"""Guided "real shop" journey: categories → products → choose → ORDER generated.

Verifies the full salesperson-style funnel end-to-end through the internal
message endpoint: the customer is shown categories first, opens a category, picks
a product, and — via the new purchase call-to-action — is walked to a persisted
order. Isolated engine + get_db override (same pattern as test_browse_flow).
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.category import Category
from app.models.product import Product, ProductVariant
from app.models.order import Order, OrderItem
from app.models.conversation import Conversation

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
    async with factory() as s:
        yield s
        await s.rollback()


@pytest_asyncio.fixture
async def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _store(db, lang="en", name="Noor Fashion"):
    s = Store(business_name=name, owner_name="O", preferred_language=lang)
    db.add(s)
    await db.flush()
    return s


async def _cat(db, sid, name, order=1):
    c = Category(store_id=sid, name=name, display_order=order, is_active=True)
    db.add(c)
    await db.flush()
    return c


async def _product(db, sid, name, cat_id, price, variants):
    p = Product(store_id=sid, name=name, category_id=cat_id, base_price=price, is_active=True)
    db.add(p)
    await db.flush()
    for color, size, stock in variants:
        db.add(ProductVariant(product_id=p.id, price=price, stock=stock,
                              color=color, size=size, is_active=True))
    await db.flush()
    return p


async def _msg(client, sid, text, customer):
    r = await client.post("/internal/whatsapp/messages",
                          json={"store_id": sid, "customer_number": customer, "message": text},
                          headers=TOKEN)
    assert r.status_code == 200, r.text
    return r.json()


async def _stage(db, sid):
    """Read the live order_stage for this store's conversation (language-agnostic)."""
    conv = (await db.execute(
        select(Conversation).where(Conversation.store_id == sid))).scalars().first()
    return conv.order_stage if conv else None


async def test_full_shop_journey_creates_order(client, db_session):
    """Hi → category → product → Order → size → qty → details → confirm → row."""
    s = await _store(db_session)
    lawn = await _cat(db_session, s.id, "Lawn", 1)
    await _cat(db_session, s.id, "Cotton", 2)
    prod = await _product(db_session, s.id, "Printed Lawn Suit", lawn.id, 3500,
                          [("white", "medium", 6), ("black", "large", 4)])
    await db_session.commit()
    cust = "923009990001"

    # 1. Greeting → seller shows categories first
    greet = await _msg(client, s.id, "Hi", cust)
    assert greet["intent"] == "category_menu"
    assert "Lawn" in greet["message"] and "Cotton" in greet["message"]

    # 2. Open the Lawn category → real products in it
    cat = await _msg(client, s.id, "1", cust)
    assert cat["intent"] == "category_products"
    assert "Printed Lawn Suit" in cat["message"]

    # 3. Pick the product → detail carries a purchase call-to-action ("Order")
    detail = await _msg(client, s.id, "1", cust)
    assert detail["matched_product_id"] == prod.id
    assert "Order" in detail["message"]  # invites the sale, in every language

    # 4. Say "Order" → guided order begins (multi-variant → awaits size)
    await _msg(client, s.id, "Order", cust)
    assert await _stage(db_session, s.id) == "PRODUCT_SELECTED"

    # 5. Provide the variant → quantity next
    await _msg(client, s.id, "white medium", cust)
    assert await _stage(db_session, s.id) == "VARIANT_SELECTED"

    # 6. Quantity → customer details next
    await _msg(client, s.id, "2", cust)
    assert await _stage(db_session, s.id) == "QUANTITY_SELECTED"

    # 7. Name + phone → address next (the fix: name/phone is NOT eaten as address)
    await _msg(client, s.id, "Ali Khan 03001234567", cust)
    assert await _stage(db_session, s.id) == "CUSTOMER_DETAILS_REQUIRED"

    # 8. Address → payment next
    await _msg(client, s.id, "House 12, Gulberg, Lahore", cust)
    assert await _stage(db_session, s.id) == "ADDRESS_REQUIRED"

    # 9. Payment → order summary / confirmation
    await _msg(client, s.id, "COD", cust)
    assert await _stage(db_session, s.id) == "ORDER_CONFIRMATION"

    # 10. Confirm → order is generated and persisted (stage then resets to
    # BROWSING, ready for the next order — the persisted row is the proof).
    await _msg(client, s.id, "haan confirm", cust)
    assert await _stage(db_session, s.id) == "BROWSING"

    orders = (await db_session.execute(
        select(Order).where(Order.store_id == s.id))).scalars().all()
    assert len(orders) == 1
    order = orders[0]
    items = (await db_session.execute(
        select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
    assert len(items) == 1
    assert items[0].product_id == prod.id
    assert items[0].quantity == 2

    # stock decremented on the chosen variant (white/medium: 6 → 4)
    chosen = (await db_session.execute(
        select(ProductVariant).where(
            ProductVariant.product_id == prod.id,
            ProductVariant.color == "white"))).scalar_one()
    assert chosen.stock == 4


async def test_single_variant_skips_size_question(client, db_session):
    """A one-variant product goes straight to quantity — no pointless size ask."""
    s = await _store(db_session, name="Cap House")
    caps = await _cat(db_session, s.id, "Caps", 1)
    prod = await _product(db_session, s.id, "Plain Black Cap", caps.id, 800,
                          [("black", "one size", 10)])
    await db_session.commit()
    cust = "923009990002"

    await _msg(client, s.id, "Hello", cust)          # category menu
    await _msg(client, s.id, "Caps", cust)           # open category by name
    detail = await _msg(client, s.id, "1", cust)     # pick product
    assert detail["matched_product_id"] == prod.id

    await _msg(client, s.id, "Order", cust)
    # single variant → skips the size question, jumps straight to quantity
    assert await _stage(db_session, s.id) == "VARIANT_SELECTED"


async def test_out_of_stock_product_is_not_offered_for_order(client, db_session):
    """Out-of-stock detail steers back to other designs, doesn't invite an order."""
    s = await _store(db_session, name="Sold Out Store")
    c = await _cat(db_session, s.id, "Shirts", 1)
    prod = await _product(db_session, s.id, "Sold Out Shirt", c.id, 1500,
                          [("blue", "medium", 0)])
    await db_session.commit()
    cust = "923009990003"

    await _msg(client, s.id, "Hi", cust)
    await _msg(client, s.id, "Shirts", cust)
    detail = await _msg(client, s.id, "1", cust)
    assert detail["matched_product_id"] == prod.id
    # steers back to other designs; never invites an order for a sold-out item
    assert "Back" in detail["message"]
    assert "'Order'" not in detail["message"]
    # and it did not start an order funnel
    assert await _stage(db_session, s.id) in ("BROWSING", None)


async def test_shop_journey_does_not_leak_across_stores(client, db_session):
    """Same customer number, two stores → each order funnel stays store-scoped."""
    s1 = await _store(db_session, name="StoreOne")
    c1 = await _cat(db_session, s1.id, "A", 1)
    p1 = await _product(db_session, s1.id, "Alpha Suit", c1.id, 1000, [("red", "M", 5)])
    s2 = await _store(db_session, name="StoreTwo")
    c2 = await _cat(db_session, s2.id, "B", 1)
    await _product(db_session, s2.id, "Beta Shirt", c2.id, 2000, [("blue", "L", 5)])
    await db_session.commit()
    cust = "923009990004"

    # Browse + pick + order in store 1 only.
    await _msg(client, s1.id, "Hi", cust)
    await _msg(client, s1.id, "A", cust)
    d = await _msg(client, s1.id, "1", cust)
    assert "Alpha Suit" in d["message"]
    assert "Beta Shirt" not in d["message"]
    await _msg(client, s1.id, "Order", cust)
    await _msg(client, s1.id, "2", cust)  # qty (single variant auto-selected)
    await _msg(client, s1.id, "Ali 03001234567", cust)
    await _msg(client, s1.id, "House 5, Model Town, Lahore", cust)
    await _msg(client, s1.id, "COD", cust)
    await _msg(client, s1.id, "haan confirm", cust)

    o1 = (await db_session.execute(select(Order).where(Order.store_id == s1.id))).scalars().all()
    o2 = (await db_session.execute(select(Order).where(Order.store_id == s2.id))).scalars().all()
    assert len(o1) == 1 and len(o2) == 0  # order belongs only to store 1
