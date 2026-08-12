"""Browse / "show me options" intent → deterministic, grounded product retrieval.

The bug being fixed: asking to see available items produced another clarification
question instead of real products. Isolated engine + get_db override.
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


async def _store(db, lang="roman_urdu", name="Noor"):
    s = Store(business_name=name, owner_name="O", preferred_language=lang)
    db.add(s)
    await db.flush()
    return s


async def _cat(db, sid, name, order=1):
    c = Category(store_id=sid, name=name, display_order=order, is_active=True)
    db.add(c)
    await db.flush()
    return c


async def _product(db, sid, name, cat_id=None, price=1000, stock=5, color="Blue", size="M"):
    p = Product(store_id=sid, name=name, category_id=cat_id, base_price=price, is_active=True)
    db.add(p)
    await db.flush()
    db.add(ProductVariant(product_id=p.id, price=price, stock=stock, color=color, size=size, is_active=True))
    await db.flush()
    return p


async def _msg(client, sid, text, customer="923001110000"):
    r = await client.post("/internal/whatsapp/messages",
                          json={"store_id": sid, "customer_number": customer, "message": text},
                          headers=TOKEN)
    assert r.status_code == 200, r.text
    return r.json()


async def _small_catalog(db):
    s = await _store(db)
    c = await _cat(db, s.id, "Lawn")
    await _product(db, s.id, "Classic Lawn Suit", c.id, price=4500, color="Blue", size="M")
    await _product(db, s.id, "Embroidered Cotton Suit", c.id, price=3800, color="Black", size="L")
    await _product(db, s.id, "Printed Kurta", None, price=2000, color="Maroon", size="S")
    await db.commit()
    return s


async def test_browse_returns_real_products_not_a_question(client, db_session):
    s = await _small_catalog(db_session)
    for phrase in ["Mujhe kuch designs dikhao", "Kya available hai", "options do", "jo available hai woh bhejo"]:
        r = await _msg(client, s.id, phrase, customer="92000000001")
        assert r["intent"] == "browse_catalog", f"{phrase!r} -> {r['intent']}"
        # real DB values present, no clarifying question
        assert "Classic Lawn Suit" in r["message"]
        assert "Rs. 4,500" in r["message"]
        assert "?" not in r["message"]  # not a question


async def test_browse_does_not_repeat_clarification_three_times(client, db_session):
    s = await _small_catalog(db_session)
    cust = "92000000002"
    r1 = await _msg(client, s.id, "Kia available hai aapka pass", customer=cust)
    r2 = await _msg(client, s.id, "Mujhe kuch designs dikha dein jo available hon", customer=cust)
    r3 = await _msg(client, s.id, "Mujhe koi options dein taake main select karun", customer=cust)
    for r in (r1, r2, r3):
        assert r["intent"] == "browse_catalog"
        assert "Classic Lawn Suit" in r["message"]


async def test_specific_product_query_not_hijacked_by_browse(client, db_session):
    s = await _small_catalog(db_session)
    r = await _msg(client, s.id, "show me Printed Kurta", customer="92000000003")
    # falls through to normal search → resolves the specific product
    assert r["matched_product_id"] is not None
    assert "Printed Kurta" in r["message"]


async def test_number_selects_from_latest_snapshot(client, db_session):
    s = await _small_catalog(db_session)
    cust = "92000000004"
    page = await _msg(client, s.id, "designs dikhao", customer=cust)
    # second item on the shown page
    second_name = None
    for line in page["message"].splitlines():
        if line.startswith("2. "):
            second_name = line[3:].strip()
    assert second_name
    r = await _msg(client, s.id, "2", customer=cust)
    assert r["intent"] == "product_search"
    assert r["matched_product_id"] is not None
    assert second_name in r["message"]


async def test_more_paginates_without_duplicates(client, db_session):
    s = await _store(db_session)
    c = await _cat(db_session, s.id, "All")
    for i in range(7):  # 7 products → page1 shows 5, "More" shows 2
        await _product(db_session, s.id, f"Design {i+1}", c.id, price=1000 + i)
    await db_session.commit()
    cust = "92000000005"
    p1 = await _msg(client, s.id, "options dikhao", customer=cust)
    p2 = await _msg(client, s.id, "More", customer=cust)
    page1_names = {ln[3:].strip() for ln in p1["message"].splitlines() if ln[:3] in {f"{n}. " for n in range(1, 6)}}
    page2_names = {ln[3:].strip() for ln in p2["message"].splitlines() if ln.startswith(("6. ", "7. "))}
    assert page2_names and page1_names.isdisjoint(page2_names)  # no duplicates
    assert "Design 6" in p2["message"]


async def test_roman_urdu_wrapper_on_browse(client, db_session):
    s = await _small_catalog(db_session)
    r = await _msg(client, s.id, "designs dikhao", customer="92000000006")
    assert "available hain" in r["message"].lower()  # Roman Urdu wrapper


async def test_empty_catalog_truthful_and_notifies(client, db_session):
    s = await _store(db_session, name="Empty")
    await db_session.commit()
    r = await _msg(client, s.id, "kya available hai", customer="92000000007")
    assert r["intent"] == "browse_catalog"
    assert "koi active product available nahi" in r["message"]
    assert r["needs_human"] is True


async def test_browse_never_leaks_across_stores(client, db_session):
    s1 = await _store(db_session, name="StoreOne")
    c1 = await _cat(db_session, s1.id, "A")
    await _product(db_session, s1.id, "Store One Suit", c1.id, price=1111)
    s2 = await _store(db_session, name="StoreTwo")
    c2 = await _cat(db_session, s2.id, "B")
    await _product(db_session, s2.id, "Store Two Shirt", c2.id, price=2222)
    await db_session.commit()

    r1 = await _msg(client, s1.id, "designs dikhao", customer="92000000008")
    assert "Store One Suit" in r1["message"]
    assert "Store Two Shirt" not in r1["message"]

    r2 = await _msg(client, s2.id, "designs dikhao", customer="92000000009")
    assert "Store Two Shirt" in r2["message"]
    assert "Store One Suit" not in r2["message"]


async def test_missing_image_does_not_crash_browse_or_detail(client, db_session):
    s = await _store(db_session)
    c = await _cat(db_session, s.id, "NoImg")
    await _product(db_session, s.id, "No Image Suit", c.id, price=999)  # image_url stays None
    await db_session.commit()
    cust = "92000000010"
    page = await _msg(client, s.id, "options dikhao", customer=cust)
    assert "No Image Suit" in page["message"]
    r = await _msg(client, s.id, "1", customer=cust)
    assert r["matched_product_id"] is not None
    assert r["image_url"] is None  # truthful: no fake image
