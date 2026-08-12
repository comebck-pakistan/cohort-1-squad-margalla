"""Customer greeting → category menu → product browse conversation flow.

Categories always come from the selected store's active catalog (never hardcoded).
Isolated in-memory engine + get_db override so nothing leaks into the shared engine.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.category import Category
from app.models.product import Product, ProductVariant

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


async def _seed_store(db, lang="english", name="Noor Fashion House"):
    s = Store(business_name=name, owner_name="Owner", preferred_language=lang)
    db.add(s)
    await db.flush()
    return s


async def _cat(db, store_id, name, order, active=True):
    c = Category(store_id=store_id, name=name, display_order=order, is_active=active)
    db.add(c)
    await db.flush()
    return c


async def _product(db, store_id, name, category_id=None, price=1000, stock=5):
    p = Product(store_id=store_id, name=name, category_id=category_id, base_price=price, is_active=True)
    db.add(p)
    await db.flush()
    db.add(ProductVariant(product_id=p.id, price=price, stock=stock, is_active=True))
    await db.flush()
    return p


async def _msg(client, store_id, text, customer="923001110000"):
    r = await client.post("/internal/whatsapp/messages",
                          json={"store_id": store_id, "customer_number": customer, "message": text},
                          headers=TOKEN)
    assert r.status_code == 200, r.text
    return r.json()


async def _setup(db):
    s = await _seed_store(db)
    cot = await _cat(db, s.id, "Cotton", 1)
    lawn = await _cat(db, s.id, "Lawn", 2)
    silk = await _cat(db, s.id, "Silk", 3)
    await _cat(db, s.id, "Wool", 4, active=False)  # inactive → hidden
    # 6 products in Cotton (to exercise pagination at page size 5)
    for i in range(6):
        await _product(db, s.id, f"Cotton Item {i+1}", category_id=cot.id, price=1000 + i)
    await _product(db, s.id, "Lawn Suit", category_id=lawn.id, price=2000)
    await db.commit()
    return s, cot, lawn, silk


async def test_greeting_shows_active_ordered_categories(client, db_session):
    s, *_ = await _setup(db_session)
    r = await _msg(client, s.id, "Hi", customer="920000000001")
    assert r["intent"] == "category_menu"
    msg = r["message"]
    assert "Cotton" in msg and "Lawn" in msg and "Silk" in msg
    assert "Wool" not in msg           # inactive hidden
    # order preserved
    assert msg.index("Cotton") < msg.index("Lawn") < msg.index("Silk")
    assert "Noor Fashion House" in msg


async def test_no_hardcoded_categories_uses_store_catalog(client, db_session):
    # A different store with its own categories.
    s2 = await _seed_store(db_session, name="Step Up Footwear")
    await _cat(db_session, s2.id, "Sneakers", 1)
    await _cat(db_session, s2.id, "Loafers", 2)
    await db_session.commit()
    r = await _msg(client, s2.id, "Hello", customer="920000000002")
    assert r["intent"] == "category_menu"
    assert "Sneakers" in r["message"] and "Loafers" in r["message"]
    assert "Cotton" not in r["message"]  # never bleeds another store's categories


async def test_number_selection_shows_category_products(client, db_session):
    s, cot, lawn, silk = await _setup(db_session)
    cust = "920000000003"
    await _msg(client, s.id, "Hi", customer=cust)          # menu: 1 Cotton, 2 Lawn, 3 Silk
    r = await _msg(client, s.id, "2", customer=cust)        # pick Lawn
    assert r["intent"] == "category_products"
    assert "Lawn Suit" in r["message"]


async def test_name_selection_and_menu_snapshot(client, db_session):
    s, *_ = await _setup(db_session)
    cust = "920000000004"
    await _msg(client, s.id, "Salam", customer=cust)
    r = await _msg(client, s.id, "show lawn", customer=cust)
    assert r["intent"] == "category_products"
    assert "Lawn Suit" in r["message"]


async def test_pagination_more_and_back(client, db_session):
    s, cot, *_ = await _setup(db_session)
    cust = "920000000005"
    await _msg(client, s.id, "Hi", customer=cust)
    page1 = await _msg(client, s.id, "1", customer=cust)    # Cotton, 6 items → page 1 shows 5
    assert page1["intent"] == "category_products"
    assert "Cotton Item 1" in page1["message"]
    assert "Cotton Item 6" not in page1["message"]
    assert "More" in page1["message"]

    page2 = await _msg(client, s.id, "More", customer=cust)
    assert "Cotton Item 6" in page2["message"]
    assert "Previous" in page2["message"]

    back = await _msg(client, s.id, "Back", customer=cust)
    assert back["intent"] == "category_menu"
    assert "Cotton" in back["message"]


async def test_product_selection_from_category_page(client, db_session):
    s, cot, *_ = await _setup(db_session)
    cust = "920000000006"
    await _msg(client, s.id, "Hi", customer=cust)
    await _msg(client, s.id, "1", customer=cust)            # Cotton page (products snapshot)
    r = await _msg(client, s.id, "1", customer=cust)        # first product on page
    assert r["intent"] == "product_search"
    assert r["matched_product_id"] is not None
    assert "Cotton Item 1" in r["message"]


async def test_direct_product_query_still_works(client, db_session):
    s, *_ = await _setup(db_session)
    cust = "920000000007"
    # even after greeting, a specific product name must reach normal search
    await _msg(client, s.id, "Hi", customer=cust)
    r = await _msg(client, s.id, "Lawn Suit", customer=cust)
    assert r["matched_product_id"] is not None
    assert "Lawn Suit" in r["message"]


async def test_greeting_without_categories_falls_back(client, db_session):
    s = await _seed_store(db_session, name="Empty Store")
    await db_session.commit()
    r = await _msg(client, s.id, "Hi", customer="920000000008")
    # no categories → normal greeting, never an empty menu
    assert r["intent"] != "category_menu"


async def test_roman_urdu_wrapper(client, db_session):
    s = await _seed_store(db_session, lang="roman_urdu", name="Noor")
    await _cat(db_session, s.id, "Cotton", 1)
    await db_session.commit()
    r = await _msg(client, s.id, "Salam", customer="920000000009")
    assert r["intent"] == "category_menu"
    # Roman Urdu wrapper text, seller category name unchanged
    assert "Cotton" in r["message"]
    assert "khush aamdeed" in r["message"].lower()
