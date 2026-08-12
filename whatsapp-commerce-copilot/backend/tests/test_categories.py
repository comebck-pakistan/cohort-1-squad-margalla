"""Category CRUD, store-isolation, product wiring, and image management.

Isolated in-memory engine + get_db override so committed rows never leak into
the shared conftest engine. Image tests use a temp UPLOAD_DIR.
"""
import io
import os
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.product import Product, ProductVariant

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module", autouse=True)
def upload_dir():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        os.environ["UPLOAD_DIR"] = d
        yield d


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


async def _store(db_session, name="Store"):
    s = Store(business_name=name, owner_name="Owner")
    db_session.add(s)
    await db_session.flush()
    return s.id


def _jpeg(color="red", w=80, h=80):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=color).save(buf, format="JPEG")
    buf.seek(0)
    return buf


# ---------- CRUD + isolation ----------

async def test_category_crud_and_ordering(client, db_session):
    sid = await _store(db_session)
    # create out of order; list must come back by display_order then name
    await client.post(f"/api/stores/{sid}/categories", json={"name": "Silk", "display_order": 3})
    await client.post(f"/api/stores/{sid}/categories", json={"name": "Cotton", "display_order": 1})
    await client.post(f"/api/stores/{sid}/categories", json={"name": "Lawn", "display_order": 2})

    r = await client.get(f"/api/stores/{sid}/categories")
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert names == ["Cotton", "Lawn", "Silk"]

    cat_id = r.json()[0]["id"]
    # get one
    one = await client.get(f"/api/stores/{sid}/categories/{cat_id}")
    assert one.status_code == 200 and one.json()["name"] == "Cotton"
    # patch rename + deactivate
    patched = await client.patch(f"/api/stores/{sid}/categories/{cat_id}",
                                 json={"name": "Pure Cotton", "is_active": False})
    assert patched.status_code == 200
    assert patched.json()["name"] == "Pure Cotton"
    assert patched.json()["is_active"] is False
    # delete (empty) ok
    d = await client.delete(f"/api/stores/{sid}/categories/{cat_id}")
    assert d.status_code == 200


async def test_duplicate_name_same_store_rejected(client, db_session):
    sid = await _store(db_session)
    a = await client.post(f"/api/stores/{sid}/categories", json={"name": "Sneakers"})
    assert a.status_code == 200
    b = await client.post(f"/api/stores/{sid}/categories", json={"name": "Sneakers"})
    assert b.status_code == 409


async def test_same_name_different_stores_allowed(client, db_session):
    s1 = await _store(db_session, "S1")
    s2 = await _store(db_session, "S2")
    a = await client.post(f"/api/stores/{s1}/categories", json={"name": "Formal"})
    b = await client.post(f"/api/stores/{s2}/categories", json={"name": "Formal"})
    assert a.status_code == 200 and b.status_code == 200


async def test_cross_store_access_blocked(client, db_session):
    s1 = await _store(db_session, "A")
    s2 = await _store(db_session, "B")
    cat = (await client.post(f"/api/stores/{s1}/categories", json={"name": "Loafers"})).json()
    # reading s1's category through s2 must 404
    r = await client.get(f"/api/stores/{s2}/categories/{cat['id']}")
    assert r.status_code == 404
    # patching through the wrong store must 404
    r2 = await client.patch(f"/api/stores/{s2}/categories/{cat['id']}", json={"name": "X"})
    assert r2.status_code == 404


# ---------- product wiring ----------

async def test_product_assignment_and_count_and_filter(client, db_session):
    sid = await _store(db_session)
    cat = (await client.post(f"/api/stores/{sid}/categories", json={"name": "Cotton"})).json()

    # create product inside the category (multipart form)
    r = await client.post(
        f"/api/stores/{sid}/products",
        data={"name": "White Cotton Kurta", "price": "1000", "stock": "5", "category_id": cat["id"]},
    )
    assert r.status_code == 200
    pid = r.json()["id"]
    assert r.json()["category_id"] == cat["id"]

    # product_count reflects assignment
    got = await client.get(f"/api/stores/{sid}/categories/{cat['id']}")
    assert got.json()["product_count"] == 1

    # filter products by category
    filtered = await client.get(f"/api/stores/{sid}/products?category_id={cat['id']}")
    assert filtered.status_code == 200
    assert [p["id"] for p in filtered.json()] == [pid]

    # an uncategorized product exists and is filterable
    await client.post(f"/api/stores/{sid}/products", data={"name": "Loose Item", "price": "500"})
    unc = await client.get(f"/api/stores/{sid}/products?category_id=uncategorized")
    assert unc.status_code == 200
    assert all(p["category_id"] is None for p in unc.json())
    assert len(unc.json()) == 1


async def test_cross_store_category_assignment_rejected(client, db_session):
    s1 = await _store(db_session, "One")
    s2 = await _store(db_session, "Two")
    cat_s2 = (await client.post(f"/api/stores/{s2}/categories", json={"name": "Silk"})).json()
    # try to create a product in s1 pointing at s2's category
    r = await client.post(
        f"/api/stores/{s1}/products",
        data={"name": "Bad", "price": "100", "category_id": cat_s2["id"]},
    )
    assert r.status_code == 400


async def test_move_product_between_categories(client, db_session):
    sid = await _store(db_session)
    c1 = (await client.post(f"/api/stores/{sid}/categories", json={"name": "A"})).json()
    c2 = (await client.post(f"/api/stores/{sid}/categories", json={"name": "B"})).json()
    p = (await client.post(f"/api/stores/{sid}/products",
                           data={"name": "Mover", "price": "100", "category_id": c1["id"]})).json()
    # move to c2
    mv = await client.patch(f"/api/stores/{sid}/products/{p['id']}/category", json={"category_id": c2["id"]})
    assert mv.status_code == 200 and mv.json()["category_id"] == c2["id"]
    # move to uncategorized (null)
    mv2 = await client.patch(f"/api/stores/{sid}/products/{p['id']}/category", json={"category_id": None})
    assert mv2.status_code == 200 and mv2.json()["category_id"] is None


async def test_populated_category_delete_returns_409(client, db_session):
    sid = await _store(db_session)
    cat = (await client.post(f"/api/stores/{sid}/categories", json={"name": "Full"})).json()
    await client.post(f"/api/stores/{sid}/products",
                      data={"name": "P", "price": "100", "category_id": cat["id"]})
    d = await client.delete(f"/api/stores/{sid}/categories/{cat['id']}")
    assert d.status_code == 409
    # product still exists
    still = await client.get(f"/api/stores/{sid}/products?category_id={cat['id']}")
    assert len(still.json()) == 1


# ---------- category images ----------

async def test_category_image_upload_replace_remove(client, db_session):
    sid = await _store(db_session)
    cat = (await client.post(f"/api/stores/{sid}/categories", json={"name": "Cover"})).json()

    up = await client.post(f"/api/stores/{sid}/categories/{cat['id']}/image",
                           files={"image": ("c.jpg", _jpeg("blue"), "image/jpeg")})
    assert up.status_code == 200
    url1 = up.json()["image_url"]
    assert url1 and url1.startswith("/uploads/")
    assert os.path.exists(os.path.join(os.environ["UPLOAD_DIR"], url1.split("/")[-1]))

    # replace
    up2 = await client.post(f"/api/stores/{sid}/categories/{cat['id']}/image",
                            files={"image": ("c2.jpg", _jpeg("green"), "image/jpeg")})
    url2 = up2.json()["image_url"]
    assert url2 != url1
    # old file cleaned up
    assert not os.path.exists(os.path.join(os.environ["UPLOAD_DIR"], url1.split("/")[-1]))

    # remove
    rm = await client.delete(f"/api/stores/{sid}/categories/{cat['id']}/image")
    assert rm.status_code == 200 and rm.json()["image_url"] is None
    assert not os.path.exists(os.path.join(os.environ["UPLOAD_DIR"], url2.split("/")[-1]))


async def test_category_image_invalid_rejected(client, db_session):
    sid = await _store(db_session)
    cat = (await client.post(f"/api/stores/{sid}/categories", json={"name": "Bad"})).json()
    r = await client.post(f"/api/stores/{sid}/categories/{cat['id']}/image",
                          files={"image": ("x.jpg", io.BytesIO(b"not an image"), "image/jpeg")})
    assert r.status_code == 400


async def test_category_image_cross_store_blocked(client, db_session):
    s1 = await _store(db_session, "I")
    s2 = await _store(db_session, "J")
    cat = (await client.post(f"/api/stores/{s1}/categories", json={"name": "Z"})).json()
    r = await client.post(f"/api/stores/{s2}/categories/{cat['id']}/image",
                          files={"image": ("z.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 404
