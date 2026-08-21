"""Catalogue picture delivery: what reaches the customer, and what never does.

Two halves, both grounded in persisted rows:

* the customer gallery — which products become pictures for a given
  category+colour, what their captions say, and that the numbers keep pointing
  at the design they were shown next to;
* the seller API — that a product cannot be declared "gallery-ready" while it is
  still missing something the caption or the filter depends on, whether the call
  comes from the dashboard or straight from curl.

Isolated in-memory engine + get_db override so committed rows never leak into
the shared session-scoped engine other test modules use.
"""
import io
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from PIL import Image as PILImage

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.category import Category
from app.models.product import Product, ProductVariant
from app.services.catalog_gallery import resolve_media_url

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


async def _store(db, name="Picture House"):
    s = Store(business_name=name, owner_name="Owner", preferred_language="english")
    db.add(s)
    await db.flush()
    return s


async def _cat(db, sid, name, order=1):
    c = Category(store_id=sid, name=name, display_order=order, is_active=True)
    db.add(c)
    await db.flush()
    return c


async def _product(db, sid, name, cat_id, price, variants,
                   image="/uploads/x.jpg", active=True):
    """variants: (color, size, stock) or (color, size, stock, active) or
    (color, size, stock, active, price)."""
    p = Product(store_id=sid, name=name, category_id=cat_id, base_price=price,
                image_url=image, is_active=active)
    db.add(p)
    await db.flush()
    for v in variants:
        db.add(ProductVariant(
            product_id=p.id,
            color=v[0], size=v[1], stock=v[2],
            is_active=v[3] if len(v) > 3 else True,
            price=v[4] if len(v) > 4 else price,
        ))
    await db.flush()
    return p


async def _msg(client, sid, text, num="923005550000"):
    r = await client.post("/internal/whatsapp/messages", headers=TOKEN, json={
        "store_id": sid, "customer_number": num, "message": text,
    })
    assert r.status_code == 200, r.text
    return r.json()


async def _decoy(db, sid, cat_id):
    """A second colour in the category, so the shop asks which colour first.

    With a single colour (or a single design) the controller sensibly skips the
    colour menu and opens the product straight away — every gallery test needs a
    real choice to exist for the customer to make.
    """
    return await _product(db, sid, "Decoy Green Kurta", cat_id, 1900,
                          [("Green", "M", 3)], image="/uploads/decoy.jpg")


async def _gallery(client, sid, cust, category="Cotton", color="Blue"):
    """Walk the real customer path: category → colour → pictures."""
    await _msg(client, sid, category, cust)
    return await _msg(client, sid, color, cust)


def _png_bytes(size=(40, 40)):
    buf = io.BytesIO()
    PILImage.new("RGB", size, (30, 90, 200)).save(buf, "PNG")
    return buf.getvalue()


# --- The customer gallery --------------------------------------------------

async def test_category_and_colour_return_matching_pictures(client, db_session):
    s = await _store(db_session)
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Blue Cotton Suit", cotton.id, 4500,
                   [("Blue", "M", 4)], image="/uploads/blue-suit.jpg")
    await _product(db_session, s.id, "Blue Cotton Kurta", cotton.id, 2600,
                   [("Blue", "M", 2)], image="/uploads/blue-kurta.jpg")
    await _product(db_session, s.id, "Red Cotton Kurta", cotton.id, 2600,
                   [("Red", "M", 2)], image="/uploads/red.jpg")
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550001")
    assert [m["caption"] for m in r["media_items"]] == [
        "1. Blue Cotton Suit\nCategory: Cotton\nColour: Blue\nPrice: PKR 4,500",
        "2. Blue Cotton Kurta\nCategory: Cotton\nColour: Blue\nPrice: PKR 2,600",
    ]
    # a different colour in the same category is never pictured
    assert "Red Cotton Kurta" not in " ".join(m["caption"] for m in r["media_items"])


async def test_another_category_is_excluded(client, db_session):
    s = await _store(db_session)
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    lawn = await _cat(db_session, s.id, "Lawn", 2)
    await _product(db_session, s.id, "Blue Cotton Kurta", cotton.id, 2600,
                   [("Blue", "M", 2)], image="/uploads/c.jpg")
    await _product(db_session, s.id, "Blue Lawn Kurta", lawn.id, 3000,
                   [("Blue", "M", 2)], image="/uploads/l.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550002")
    captions = " ".join(m["caption"] for m in r["media_items"])
    assert "Blue Cotton Kurta" in captions
    assert "Blue Lawn Kurta" not in captions


@pytest.mark.parametrize("label,kwargs,variants", [
    ("inactive product", {"active": False}, [("Blue", "M", 3)]),
    ("inactive variant", {}, [("Blue", "M", 3, False)]),
    ("out of stock", {}, [("Blue", "M", 0)]),
])
async def test_unsellable_records_are_never_pictured(client, db_session, label, kwargs, variants):
    s = await _store(db_session, name=f"House {label}")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Good Blue Kurta", cotton.id, 2600,
                   [("Blue", "M", 5)], image="/uploads/good.jpg")
    await _product(db_session, s.id, f"Bad {label} Kurta", cotton.id, 2600,
                   variants, image="/uploads/bad.jpg", **kwargs)
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, f"92300555{abs(hash(label)) % 10000:04d}")
    captions = " ".join(m["caption"] for m in r["media_items"])
    assert "Good Blue Kurta" in captions
    assert f"Bad {label} Kurta" not in captions


async def test_one_incomplete_record_does_not_block_the_valid_ones(client, db_session):
    """A row missing its picture is skipped, not fatal — and the rest still go."""
    s = await _store(db_session, name="Mixed House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Complete One", cotton.id, 2000,
                   [("Blue", "M", 3)], image="/uploads/1.jpg")
    await _product(db_session, s.id, "No Picture", cotton.id, 2200,
                   [("Blue", "M", 3)], image=None)
    await _product(db_session, s.id, "Complete Two", cotton.id, 2400,
                   [("Blue", "M", 3)], image="/uploads/2.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550003")
    names = [m["caption"].splitlines()[0] for m in r["media_items"]]
    assert names == ["1. Complete One", "3. Complete Two"]
    # skipped, but not hidden — still listed and still selectable by its number
    assert "2. No Picture" in r["message"]
    sel = await _msg(client, s.id, "2", "923005550003")
    assert "No Picture" in sel["message"]


async def test_incomplete_records_never_produce_a_partial_caption(client, db_session):
    """A pictured product with no sellable price is skipped, not sent as PKR 0."""
    s = await _store(db_session, name="Zero Price House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Priced Kurta", cotton.id, 2000,
                   [("Blue", "M", 3)], image="/uploads/ok.jpg")
    await _product(db_session, s.id, "Unpriced Kurta", cotton.id, 0,
                   [("Blue", "M", 3, True, 0)], image="/uploads/zero.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550004")
    captions = [m["caption"] for m in r["media_items"]]
    assert captions == ["1. Priced Kurta\nCategory: Cotton\nColour: Blue\nPrice: PKR 2,000"]
    assert "PKR 0" not in r["message"]
    assert not any("PKR 0" in c for c in captions)


async def test_caption_price_comes_from_the_selected_colour_variant(client, db_session):
    """Two colours, two prices — the caption must quote the one being shown."""
    s = await _store(db_session, name="Two Price House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Two Tone Kurta", cotton.id, 1000,
                   [("Blue", "M", 3, True, 5200), ("Red", "M", 3, True, 1800)],
                   image="/uploads/tt.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550005")
    assert r["media_items"][0]["caption"].endswith("Price: PKR 5,200")


async def test_media_items_carry_the_ids_and_absolute_url(client, db_session):
    s = await _store(db_session, name="Id House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    p = await _product(db_session, s.id, "Blue Kurta", cotton.id, 2600,
                       [("Blue", "M", 3)], image="/uploads/rel.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550006")
    item = r["media_items"][0]
    assert item["product_id"] == p.id
    assert item["variant_id"] == p.variants[0].id
    assert item["selection_number"] == 1
    # A relative path is unreachable for WhatsApp's fetcher.
    assert item["image_url"] == resolve_media_url("/uploads/rel.jpg")
    assert item["image_url"].startswith("http")


async def test_number_selects_the_product_that_was_pictured(client, db_session):
    s = await _store(db_session, name="Select House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    for i in range(3):
        await _product(db_session, s.id, f"Blue Design {i+1}", cotton.id, 1000 + i * 100,
                       [("Blue", "M", 3)], image=f"/uploads/b{i}.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()
    cust = "923005550007"

    r = await _gallery(client, s.id, cust)
    third = r["media_items"][2]
    assert third["selection_number"] == 3

    sel = await _msg(client, s.id, "3", cust)
    assert sel["matched_product_id"] == third["product_id"]
    assert "Blue Design 3" in sel["message"]


async def test_pagination_keeps_numbering_and_selection_aligned(client, db_session):
    s = await _store(db_session, name="Paged House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    for i in range(7):
        await _product(db_session, s.id, f"Blue Design {i+1}", cotton.id, 1000 + i,
                       [("Blue", "M", 3)], image=f"/uploads/p{i}.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()
    cust = "923005550008"

    p1 = await _gallery(client, s.id, cust)
    assert [m["selection_number"] for m in p1["media_items"]] == [1, 2, 3, 4, 5]

    p2 = await _msg(client, s.id, "More", cust)
    assert [m["selection_number"] for m in p2["media_items"]] == [6, 7]
    # the caption's own number agrees with the field
    assert p2["media_items"][0]["caption"].startswith("6. ")

    sel = await _msg(client, s.id, "7", cust)
    assert sel["matched_product_id"] == p2["media_items"][1]["product_id"]


async def test_no_pictures_at_all_falls_back_to_truthful_text(client, db_session):
    """Nothing is gallery-ready → a real numbered list, and no empty gallery."""
    s = await _store(db_session, name="Text Only House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Plain Kurta", cotton.id, 2000,
                   [("Blue", "M", 3)], image=None)
    await _product(db_session, s.id, "Plain Suit", cotton.id, 3000,
                   [("Blue", "M", 3)], image=None)
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550009")
    assert r["media_items"] == []
    assert r["media_footer"] is None
    assert "1. Plain Kurta" in r["message"] and "2. Plain Suit" in r["message"]
    # the navigation still reaches the customer, inside the single text
    assert "number" in r["message"].lower()


async def test_the_footer_is_not_repeated_in_any_caption(client, db_session):
    s = await _store(db_session, name="Footer House")
    cotton = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Blue Kurta", cotton.id, 2600,
                   [("Blue", "M", 3)], image="/uploads/f.jpg")
    await _product(db_session, s.id, "Blue Suit", cotton.id, 3600,
                   [("Blue", "M", 3)], image="/uploads/g.jpg")
    await _decoy(db_session, s.id, cotton.id)
    await db_session.commit()

    r = await _gallery(client, s.id, "923005550010")
    assert "Reply with a number" in r["media_footer"]
    for m in r["media_items"]:
        assert "Reply with a number" not in m["caption"]
        assert "'Back'" not in m["caption"]


# --- The seller API cannot be bypassed -------------------------------------

async def _create(client, sid, data, files=None):
    return await client.post(f"/api/stores/{sid}/products", data=data, files=files)


async def test_direct_api_cannot_create_an_incomplete_gallery_product(client, db_session):
    s = await _store(db_session, name="API House")
    await db_session.commit()

    r = await _create(client, s.id, {
        "name": "Blue Kurta", "price": "2500", "stock": "3", "gallery_ready": "true",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["message"] == "Product is not ready for the picture catalogue"
    # every genuinely missing field is named, so the form can mark each input
    assert set(detail["fields"]) == {"category_id", "image", "color"}


@pytest.mark.parametrize("field,overrides", [
    ("name", {"name": "test"}),
    ("name", {"name": "  "}),
    ("price", {"price": "0"}),
    ("price", {"price": "-5"}),
    ("stock", {"stock": "0"}),
    ("color", {"color": ""}),
])
async def test_each_required_gallery_field_is_enforced(client, db_session, field, overrides):
    s = await _store(db_session, name=f"Field House {field} {overrides}")
    c = await _cat(db_session, s.id, "Cotton", 1)
    await db_session.commit()

    data = {"name": "Blue Kurta", "price": "2500", "stock": "3", "color": "Blue",
            "category_id": c.id, "gallery_ready": "true"}
    data.update(overrides)
    r = await _create(client, s.id, data,
                      files={"image": ("p.png", _png_bytes(), "image/png")})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    # Values that are invalid for ANY product (blank name, negative price) are
    # caught by the pre-existing scalar validation and come back as a plain
    # message; values that are merely not good enough for the picture catalogue
    # come back in the per-field map. Both are rejections — assert on whichever
    # shape this input produces, and that it names the offending field.
    if isinstance(detail, dict):
        assert field in detail["fields"], detail
    else:
        assert field in detail.lower(), detail


async def test_invalid_category_is_rejected(client, db_session):
    s = await _store(db_session, name="Bad Cat House")
    await db_session.commit()

    r = await _create(client, s.id, {
        "name": "Blue Kurta", "price": "2500", "stock": "3", "color": "Blue",
        "category_id": "does-not-exist", "gallery_ready": "true",
    }, files={"image": ("p.png", _png_bytes(), "image/png")})
    assert r.status_code == 400


async def test_a_corrupt_image_is_rejected(client, db_session):
    s = await _store(db_session, name="Corrupt House")
    c = await _cat(db_session, s.id, "Cotton", 1)
    await db_session.commit()

    r = await _create(client, s.id, {
        "name": "Blue Kurta", "price": "2500", "stock": "3", "color": "Blue",
        "category_id": c.id, "gallery_ready": "true",
    }, files={"image": ("p.jpg", b"this is not an image", "image/jpeg")})
    assert r.status_code == 400
    assert "image" in str(r.json()["detail"]).lower()


async def test_a_complete_product_saves_and_is_gallery_ready(client, db_session):
    s = await _store(db_session, name="Happy House")
    c = await _cat(db_session, s.id, "Cotton", 1)
    await db_session.commit()

    r = await _create(client, s.id, {
        "name": "Premium Cotton Suit", "price": "4500", "stock": "6", "color": "Blue",
        "category_id": c.id, "gallery_ready": "true",
    }, files={"image": ("p.png", _png_bytes(), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gallery_ready"] is True
    assert body["gallery_blockers"] == {}
    assert body["image_url"].startswith("/uploads/")
    # the colour reached the variant, which is what the gallery filters on
    assert body["variants"][0]["color"] == "Blue"


async def test_an_update_cannot_declare_an_incomplete_product_ready(client, db_session):
    s = await _store(db_session, name="Patch House")
    p = await _product(db_session, s.id, "Legacy Kurta", None, 2000,
                       [(None, "M", 3)], image=None)
    await db_session.commit()

    r = await client.patch(f"/api/stores/{s.id}/products/{p.id}",
                           json={"name": "Nicer Kurta", "gallery_ready": True})
    assert r.status_code == 400
    fields = r.json()["detail"]["fields"]
    assert set(fields) >= {"category_id", "image", "color"}


async def test_a_historical_text_only_product_is_still_editable(client, db_session):
    """Editing an incomplete legacy product must keep working — it is only
    marked not-gallery-ready, never blocked."""
    s = await _store(db_session, name="Legacy House")
    p = await _product(db_session, s.id, "Legacy Kurta", None, 2000,
                       [(None, "M", 3)], image=None)
    await db_session.commit()

    r = await client.patch(f"/api/stores/{s.id}/products/{p.id}",
                           json={"name": "Renamed Legacy Kurta", "price": 2200})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed Legacy Kurta"
    assert body["gallery_ready"] is False
    assert "image" in body["gallery_blockers"]


async def test_an_edit_can_complete_a_legacy_product(client, db_session):
    """The seller path out of "not gallery-ready": set what is missing."""
    s = await _store(db_session, name="Fixup House")
    c = await _cat(db_session, s.id, "Cotton", 1)
    p = await _product(db_session, s.id, "Legacy Kurta", None, 2000,
                       [(None, "M", 3)], image=None)
    await _decoy(db_session, s.id, c.id)
    await db_session.commit()

    up = await client.put(f"/api/stores/{s.id}/products/{p.id}/image",
                          files={"image": ("p.png", _png_bytes(), "image/png")})
    assert up.status_code == 200, up.text

    r = await client.patch(f"/api/stores/{s.id}/products/{p.id}", json={
        "category_id": c.id, "color": "Blue", "gallery_ready": True,
    })
    assert r.status_code == 200, r.text
    assert r.json()["gallery_ready"] is True

    # …and it now actually reaches the customer as a picture
    g = await _gallery(client, s.id, "923005550011")
    assert [m["caption"].splitlines()[0] for m in g["media_items"]] == ["1. Legacy Kurta"]
