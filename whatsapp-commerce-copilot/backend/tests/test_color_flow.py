"""Category → colour menu → numbered image gallery → design selection.

Everything is grounded in the seller's own catalogue: colours come from active,
in-stock variants of that store's products, and the numbers the customer replies
with resolve against exactly the designs that were sent.

Isolated in-memory engine + get_db override so committed rows never leak into
the shared session-scoped engine other test modules use.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.category import Category
from app.models.conversation import Conversation
from app.models.product import Product, ProductVariant
from app.services.catalog_gallery import resolve_media_url
from sqlalchemy import select

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


async def _store(db, name="Noor Fashion House", lang="english"):
    s = Store(business_name=name, owner_name="Owner", preferred_language=lang)
    db.add(s)
    await db.flush()
    return s


async def _cat(db, sid, name, order=1):
    c = Category(store_id=sid, name=name, display_order=order, is_active=True)
    db.add(c)
    await db.flush()
    return c


async def _product(db, sid, name, cat_id, price, variants, image="/uploads/x.jpg"):
    """variants: list of (color, size, stock) — or (color, size, stock, active)."""
    p = Product(store_id=sid, name=name, category_id=cat_id, base_price=price,
                image_url=image, is_active=True)
    db.add(p)
    await db.flush()
    for v in variants:
        color, size, stock = v[0], v[1], v[2]
        active = v[3] if len(v) > 3 else True
        db.add(ProductVariant(product_id=p.id, price=price, stock=stock,
                              color=color, size=size, is_active=active))
    await db.flush()
    return p


async def _msg(client, sid, text, customer):
    r = await client.post("/internal/whatsapp/messages",
                          json={"store_id": sid, "customer_number": customer, "message": text},
                          headers=TOKEN)
    assert r.status_code == 200, r.text
    return r.json()


async def _cotton_store(db, name="Noor Fashion House"):
    """Cotton: 2 black designs, 1 blue, 1 white. Lawn: a single design."""
    s = await _store(db, name=name)
    cotton = await _cat(db, s.id, "Cotton", 1)
    lawn = await _cat(db, s.id, "Lawn", 2)
    await _product(db, s.id, "Black Cotton Kurta", cotton.id, 2500,
                   [("Black", "S", 3), ("Black", "M", 4), ("Black", "L", 2)],
                   image="/uploads/black-cotton-1.jpg")
    await _product(db, s.id, "Black Cotton Suit", cotton.id, 3200,
                   [("Black", "M", 5)], image="/uploads/black-cotton-2.jpg")
    await _product(db, s.id, "Blue Cotton Kurta", cotton.id, 2400,
                   [("Blue", "M", 6)], image="/uploads/blue-cotton-1.jpg")
    await _product(db, s.id, "White Cotton Suit", cotton.id, 2900,
                   [("White", "L", 2)], image="/uploads/white-cotton-1.jpg")
    await _product(db, s.id, "Lawn Piece", lawn.id, 1800, [("Green", "M", 4)])
    await db.commit()
    return s, cotton, lawn


# --- 1. Category opens on a colour menu, not a product dump -----------------

async def test_category_asks_for_colour_first(client, db_session):
    s, *_ = await _cotton_store(db_session)
    r = await _msg(client, s.id, "Cotton dikhao", "923001000001")
    assert r["intent"] == "category_colors"
    msg = r["message"]
    assert "Black" in msg and "Blue" in msg and "White" in msg
    assert "1." in msg and "2." in msg and "3." in msg
    # the colour menu is a question about colour, not a list of designs
    assert "Black Cotton Kurta" not in msg
    assert r["media_items"] == []


async def test_colour_menu_only_lists_sellable_colours(client, db_session):
    s = await _store(db_session, name="Stock Test House")
    c = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "In Stock A", c.id, 1000, [("Black", "M", 5)])
    await _product(db_session, s.id, "In Stock B", c.id, 1100, [("Blue", "M", 2)])
    await _product(db_session, s.id, "Sold Out", c.id, 1200, [("Maroon", "M", 0)])
    await _product(db_session, s.id, "Retired", c.id, 1300, [("Purple", "M", 9, False)])
    await db_session.commit()
    r = await _msg(client, s.id, "Cotton", "923001000002")
    assert r["intent"] == "category_colors"
    assert "Black" in r["message"] and "Blue" in r["message"]
    assert "Maroon" not in r["message"]   # out of stock
    assert "Purple" not in r["message"]   # inactive variant


async def test_single_colour_category_skips_the_menu(client, db_session):
    s, cotton, lawn = await _cotton_store(db_session)
    r = await _msg(client, s.id, "Lawn", "923001000003")
    # one design, one colour → nothing to choose, go straight to the product page
    assert r["intent"] == "category_products"
    assert "Lawn Piece" in r["message"]


# --- 2/3/5. Colour selection filters the catalogue and returns images -------

async def test_colour_selection_returns_numbered_images(client, db_session):
    s, *_ = await _cotton_store(db_session)
    cust = "923001000004"
    await _msg(client, s.id, "Cotton dikhao", cust)
    r = await _msg(client, s.id, "Black", cust)

    assert r["intent"] == "color_products"
    media = r["media_items"]
    assert len(media) == 2
    assert [m["caption"] for m in media] == [
        "1. Black Cotton Kurta\nCategory: Cotton\nColour: Black\nPrice: PKR 2,500",
        "2. Black Cotton Suit\nCategory: Cotton\nColour: Black\nPrice: PKR 3,200",
    ]
    # WhatsApp fetches the picture itself, so the URL must be absolute.
    assert [m["image_url"] for m in media] == [
        resolve_media_url("/uploads/black-cotton-1.jpg"),
        resolve_media_url("/uploads/black-cotton-2.jpg"),
    ]
    assert all(m["image_url"].startswith("http") for m in media)
    assert all(m["product_id"] and m["variant_id"] for m in media)
    # the number in the caption is carried explicitly for selection mapping
    assert [m["selection_number"] for m in media] == [1, 2]
    # never leaks the other colours in this category
    joined = r["message"] + " ".join(m["caption"] for m in media)
    assert "Blue Cotton Kurta" not in joined and "White Cotton Suit" not in joined
    # the prompt is sent after the gallery, so it is kept separate
    assert "number" in r["media_footer"].lower()


async def test_colour_selection_by_number_matches_the_shown_menu(client, db_session):
    s, *_ = await _cotton_store(db_session)
    cust = "923001000005"
    menu = await _msg(client, s.id, "Cotton", cust)
    # read the number the customer actually saw next to "Blue"
    n = next(l.split(".")[0] for l in menu["message"].splitlines() if l.strip().endswith("Blue"))
    r = await _msg(client, s.id, n.strip(), cust)
    assert r["intent"] == "color_products"
    assert [m["caption"] for m in r["media_items"]] == [
        "1. Blue Cotton Kurta\nCategory: Cotton\nColour: Blue\nPrice: PKR 2,400"]


async def test_colour_flow_never_crosses_stores(client, db_session):
    s1, *_ = await _cotton_store(db_session, name="StoreOne")
    s2 = await _store(db_session, name="StoreTwo")
    c2 = await _cat(db_session, s2.id, "Cotton", 1)
    await _product(db_session, s2.id, "Other Store Black Kurta", c2.id, 999,
                   [("Black", "M", 3)], image="/uploads/other.jpg")
    await db_session.commit()

    await _msg(client, s1.id, "Cotton", "923001000006")
    r = await _msg(client, s1.id, "Black", "923001000006")
    captions = " ".join(m["caption"] for m in r["media_items"])
    assert "Other Store Black Kurta" not in captions
    assert "Black Cotton Kurta" in captions


# --- 4/7. Design selection and pagination ----------------------------------

async def test_number_selects_the_design_that_was_pictured(client, db_session):
    s, *_ = await _cotton_store(db_session)
    cust = "923001000007"
    await _msg(client, s.id, "Cotton", cust)
    gallery = await _msg(client, s.id, "Black", cust)
    second_id = gallery["media_items"][1]["product_id"]

    r = await _msg(client, s.id, "2", cust)
    assert r["matched_product_id"] == second_id
    assert "Black Cotton Suit" in r["message"]
    # sizes come back as plain text; the picture was just sent, so it is not resent
    assert "M" in r["message"]
    assert r["image_url"] is None
    assert r["media_items"] == []


async def test_gallery_pages_at_five_images(client, db_session):
    s = await _store(db_session, name="Big Cotton House")
    c = await _cat(db_session, s.id, "Cotton", 1)
    for i in range(7):
        await _product(db_session, s.id, f"Black Design {i+1}", c.id, 1000 + i,
                       [("Black", "M", 3)], image=f"/uploads/black-{i+1}.jpg")
    await _product(db_session, s.id, "Blue Design", c.id, 1500,
                   [("Blue", "M", 3)], image="/uploads/blue.jpg")
    await db_session.commit()
    cust = "923001000008"

    await _msg(client, s.id, "Cotton", cust)
    p1 = await _msg(client, s.id, "Black", cust)
    assert len(p1["media_items"]) == 5
    assert "More" in p1["media_footer"]
    assert [m["caption"].split(".")[0] for m in p1["media_items"]] == ["1", "2", "3", "4", "5"]

    p2 = await _msg(client, s.id, "More", cust)
    assert [m["caption"].split(".")[0] for m in p2["media_items"]] == ["6", "7"]
    p1_ids = {m["product_id"] for m in p1["media_items"]}
    assert p1_ids.isdisjoint({m["product_id"] for m in p2["media_items"]})

    # numbering on page 2 still resolves against what was shown
    r = await _msg(client, s.id, "6", cust)
    assert r["matched_product_id"] == p2["media_items"][0]["product_id"]


async def test_back_from_gallery_returns_to_colours(client, db_session):
    s, *_ = await _cotton_store(db_session)
    cust = "923001000009"
    await _msg(client, s.id, "Cotton", cust)
    await _msg(client, s.id, "Black", cust)
    back = await _msg(client, s.id, "Back", cust)
    assert back["intent"] == "category_colors"
    assert "Blue" in back["message"]


async def test_products_without_pictures_stay_in_the_text(client, db_session):
    s = await _store(db_session, name="Mixed Media House")
    c = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Pictured Kurta", c.id, 2000,
                   [("Black", "M", 3)], image="/uploads/pic.jpg")
    await _product(db_session, s.id, "Unpictured Kurta", c.id, 2200,
                   [("Black", "M", 3)], image=None)
    await _product(db_session, s.id, "Blue Kurta", c.id, 2100,
                   [("Blue", "M", 3)], image="/uploads/blue.jpg")
    await db_session.commit()
    cust = "923001000010"

    await _msg(client, s.id, "Cotton", cust)
    r = await _msg(client, s.id, "Black", cust)
    assert [m["caption"] for m in r["media_items"]] == [
        "1. Pictured Kurta\nCategory: Cotton\nColour: Black\nPrice: PKR 2,000"]
    assert "2. Unpictured Kurta" in r["message"]   # nothing silently dropped
    # and the text entry is still selectable by its number
    sel = await _msg(client, s.id, "2", cust)
    assert "Unpictured Kurta" in sel["message"]


# --- 10. The rest of the funnel stays text-only ----------------------------

async def test_order_steps_after_the_gallery_are_text_only(client, db_session):
    s, *_ = await _cotton_store(db_session)
    cust = "923001000011"
    await _msg(client, s.id, "Cotton", cust)
    await _msg(client, s.id, "Black", cust)
    await _msg(client, s.id, "1", cust)                    # Black Cotton Kurta (S/M/L)
    size = await _msg(client, s.id, "Order", cust)
    assert size["media_items"] == []
    qty = await _msg(client, s.id, "M", cust)
    assert qty["media_items"] == []
    assert qty["media_footer"] is None


async def _stage(db, sid):
    """Live order_stage for this store's conversation (language-agnostic)."""
    conv = (await db.execute(
        select(Conversation).where(Conversation.store_id == sid))).scalars().first()
    return conv.order_stage if conv else None


async def test_bare_size_reply_advances_to_quantity(client, db_session):
    """The size question lists S/M/L, so "M" is an answer — not a dead end."""
    s, *_ = await _cotton_store(db_session, name="Size Reply House")
    cust = "923001000012"
    await _msg(client, s.id, "Cotton", cust)
    await _msg(client, s.id, "Black", cust)
    await _msg(client, s.id, "1", cust)          # Black Cotton Kurta: S, M, L
    await _msg(client, s.id, "Order", cust)
    assert await _stage(db_session, s.id) == "PRODUCT_SELECTED"

    await _msg(client, s.id, "M", cust)
    assert await _stage(db_session, s.id) == "VARIANT_SELECTED"
    await _msg(client, s.id, "2", cust)
    assert await _stage(db_session, s.id) == "QUANTITY_SELECTED"


async def test_size_reply_matches_however_the_seller_spelled_it(client, db_session):
    """Customer says "medium", the catalogue says "M" — same size."""
    s = await _store(db_session, name="Spelling House")
    c = await _cat(db_session, s.id, "Cotton", 1)
    await _product(db_session, s.id, "Kurta A", c.id, 2000,
                   [("Black", "M", 3), ("Black", "L", 3)])
    await _product(db_session, s.id, "Kurta B", c.id, 2100, [("Blue", "M", 3)])
    await db_session.commit()
    cust = "923001000013"
    await _msg(client, s.id, "Cotton", cust)
    await _msg(client, s.id, "Black", cust)
    await _msg(client, s.id, "1", cust)
    await _msg(client, s.id, "Order", cust)
    await _msg(client, s.id, "medium", cust)
    assert await _stage(db_session, s.id) == "VARIANT_SELECTED"


async def test_navigation_words_are_never_read_as_a_size(client, db_session):
    """"Order"/"Back" must not be swallowed by the label matcher."""
    s, *_ = await _cotton_store(db_session, name="Nav Words House")
    cust = "923001000014"
    await _msg(client, s.id, "Cotton", cust)
    await _msg(client, s.id, "Black", cust)
    await _msg(client, s.id, "1", cust)
    await _msg(client, s.id, "Order", cust)
    # still waiting on the size — "Order" did not answer the question
    assert await _stage(db_session, s.id) == "PRODUCT_SELECTED"
    await _msg(client, s.id, "Back", cust)
    assert await _stage(db_session, s.id) == "PRODUCT_SELECTED"
