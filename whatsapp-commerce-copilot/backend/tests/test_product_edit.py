"""Editing a product's details (PATCH /products/{id}).

The catalog could create and delete products but never edit them, so a typo in a
name or a price change meant deleting and re-adding. Validation must match
create_product exactly: an edit cannot write a value that could not be created.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.product import Product, ProductVariant

pytestmark = pytest.mark.asyncio


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


async def _store(db, name="Noor"):
    s = Store(business_name=name, owner_name="O", preferred_language="en")
    db.add(s)
    await db.flush()
    return s


async def _product(db, store, name="Lawn Suit", price=3500, sku=None, variants=1):
    p = Product(store_id=store.id, name=name, base_price=price, sku=sku, is_active=True)
    db.add(p)
    await db.flush()
    for i in range(variants):
        db.add(ProductVariant(product_id=p.id, price=price, stock=5,
                              color="white", size=f"s{i}", is_active=True))
    await db.flush()
    return p


def _url(sid, pid):
    return f"/api/stores/{sid}/products/{pid}"


async def test_edit_name_description_and_price(client, db_session):
    s = await _store(db_session)
    p = await _product(db_session, s)
    await db_session.commit()

    r = await client.patch(_url(s.id, p.id), json={
        "name": "Printed Lawn Suit", "description": "3-piece unstitched", "price": 4200,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Printed Lawn Suit"
    assert body["description"] == "3-piece unstitched"
    assert body["base_price"] == 4200


async def test_partial_edit_leaves_other_fields_untouched(client, db_session):
    s = await _store(db_session, "Partial")
    p = await _product(db_session, s, name="Keep Me", price=1000)
    await db_session.commit()

    r = await client.patch(_url(s.id, p.id), json={"price": 1500})
    assert r.status_code == 200
    assert r.json()["name"] == "Keep Me"
    assert r.json()["base_price"] == 1500


async def test_single_variant_price_follows_the_product_price(client, db_session):
    """A one-variant product would otherwise still sell at the old price."""
    s = await _store(db_session, "OneVariant")
    p = await _product(db_session, s, price=1000, variants=1)
    await db_session.commit()

    await client.patch(_url(s.id, p.id), json={"price": 1800})
    v = (await db_session.execute(
        select(ProductVariant).where(ProductVariant.product_id == p.id))).scalars().one()
    await db_session.refresh(v)
    assert v.price == 1800


async def test_multi_variant_prices_are_not_overwritten(client, db_session):
    s = await _store(db_session, "MultiVariant")
    p = await _product(db_session, s, price=1000, variants=2)
    await db_session.commit()

    await client.patch(_url(s.id, p.id), json={"price": 1800})
    prices = [v.price for v in (await db_session.execute(
        select(ProductVariant).where(ProductVariant.product_id == p.id))).scalars().all()]
    assert prices == [1000, 1000], "per-variant pricing must be preserved"


@pytest.mark.parametrize("payload", [
    {"name": "   "},                 # blank name
    {"name": "x" * 256},             # too long
    {"price": -1},                   # negative price
    {"description": "d" * 5001},     # too long
    {"sku": "s" * 101},              # too long
])
async def test_invalid_edits_are_rejected(client, db_session, payload):
    s = await _store(db_session, f"Invalid{list(payload)[0]}")
    p = await _product(db_session, s)
    await db_session.commit()
    r = await client.patch(_url(s.id, p.id), json=payload)
    assert r.status_code == 400, r.text


async def test_duplicate_sku_within_store_is_rejected(client, db_session):
    s = await _store(db_session, "Skus")
    await _product(db_session, s, name="First", sku="SKU-1")
    p2 = await _product(db_session, s, name="Second", sku="SKU-2")
    await db_session.commit()

    r = await client.patch(_url(s.id, p2.id), json={"sku": "SKU-1"})
    assert r.status_code == 400


async def test_keeping_its_own_sku_is_allowed(client, db_session):
    s = await _store(db_session, "SameSku")
    p = await _product(db_session, s, sku="KEEP-1")
    await db_session.commit()
    r = await client.patch(_url(s.id, p.id), json={"sku": "KEEP-1", "price": 999})
    assert r.status_code == 200


async def test_cannot_edit_another_stores_product(client, db_session):
    a = await _store(db_session, "OwnerA")
    b = await _store(db_session, "OwnerB")
    p = await _product(db_session, a, name="A Product")
    await db_session.commit()

    r = await client.patch(_url(b.id, p.id), json={"name": "Hijacked"})
    assert r.status_code == 404
    await db_session.refresh(p)
    assert p.name == "A Product"


async def test_unknown_product_is_404(client, db_session):
    s = await _store(db_session, "Missing")
    await db_session.commit()
    r = await client.patch(_url(s.id, "no-such-product"), json={"name": "x"})
    assert r.status_code == 404


async def test_editing_a_product_does_not_reorder_the_catalog(client, db_session):
    """Without stable ordering an edited row jumps to the end of the seller's grid."""
    s = await _store(db_session, "Ordering")
    for n in ("First", "Second", "Third"):
        await _product(db_session, s, name=n)
    await db_session.commit()

    before = [p["name"] for p in (await client.get(f"/api/stores/{s.id}/products")).json()]
    target = (await client.get(f"/api/stores/{s.id}/products")).json()[0]["id"]
    await client.patch(_url(s.id, target), json={"price": 4321})
    after = [p["name"] for p in (await client.get(f"/api/stores/{s.id}/products")).json()]
    assert before == after
