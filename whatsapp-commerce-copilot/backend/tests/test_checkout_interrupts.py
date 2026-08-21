"""Questions asked in the MIDDLE of checkout.

A customer half-way through an order is still a person having a conversation:
they ask for the picture, the price, whether medium is in stock. Before the
interrupt routing existed, every message received during checkout was treated as
an answer to the current order field and `_advance_order` replaced the real
answer with `get_next_prompt()` — so the assistant repeated itself and looked
hard-coded even with a working LLM.

These tests pin down the two halves of the contract:
  * an interrupt is ANSWERED from persisted rows and never consumes the field;
  * order state — stage, product, variant, quantity, collected details — is
    identical before and after.

Isolated in-memory engine + get_db override so committed rows never leak into
the shared session-scoped engine other test modules use.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.category import Category
from app.models.conversation import Conversation
from app.models.product import Product, ProductVariant
from app.services import conversation_controller as cc
from app.services.ai_provider import MockAIProvider
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


async def _shop(db, image="/uploads/kurta.jpg", stock=5, size="M"):
    s = Store(business_name="Interrupt House", owner_name="O", preferred_language="english")
    db.add(s)
    await db.flush()
    c = Category(store_id=s.id, name="Cotton", display_order=1, is_active=True)
    db.add(c)
    await db.flush()
    p = Product(store_id=s.id, name="Blue Cotton Kurta", category_id=c.id,
                base_price=2500, image_url=image, is_active=True)
    db.add(p)
    await db.flush()
    db.add(ProductVariant(product_id=p.id, color="Blue", size=size,
                          price=2500, stock=stock, is_active=True))
    await db.flush()
    await db.commit()
    return s, p


async def _msg(client, sid, text, cust):
    r = await client.post("/internal/whatsapp/messages", headers=TOKEN, json={
        "store_id": sid, "customer_number": cust, "message": text,
    })
    assert r.status_code == 200, r.text
    return r.json()


async def _convo(db, sid):
    return (await db.execute(
        select(Conversation).where(Conversation.store_id == sid)
    )).scalars().first()


async def _at_customer_details(client, db, sid, product, cust):
    """Drive checkout to the point where name and phone are being requested."""
    await _msg(client, sid, "Blue Cotton Kurta", cust)
    await _msg(client, sid, "Order", cust)
    await _msg(client, sid, "1", cust)
    convo = await _convo(db, sid)
    await db.refresh(convo)
    assert convo.order_stage == "QUANTITY_SELECTED"
    return convo


def _state(convo):
    """Everything an interrupt is forbidden to touch."""
    return (convo.order_stage, convo.current_product_id, convo.current_variant_id,
            convo.quantity, convo.customer_name, convo.customer_phone,
            convo.customer_address, convo.payment_method)


# --- Picture requests ------------------------------------------------------

@pytest.mark.parametrize("phrase", [
    "Send me the picture",      # English — the exact reported message
    "picture bhejo",            # Roman Urdu
    "iski pic dikhao",          # Roman Urdu, possessive
    "تصویر بھیجیں",             # Urdu script
])
async def test_picture_request_during_checkout_sends_the_real_picture(
        client, db_session, phrase):
    s, p = await _shop(db_session)
    cust = f"9230011{abs(hash(phrase)) % 10000:04d}"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    before = _state(convo)

    r = await _msg(client, s.id, phrase, cust)

    assert r["intent"] == "picture_request"
    # The picture is the persisted catalogue image, made absolute for WhatsApp.
    assert r["image_url"] == resolve_media_url("/uploads/kurta.jpg")
    assert r["matched_product_id"] == p.id
    # Caption carries the real product facts…
    assert "Blue Cotton Kurta" in r["message"]
    assert "Blue" in r["message"] and "PKR 2,500" in r["message"]
    # …and the outstanding question, in the customer's own language, so they
    # know what is still needed.
    reminder = r["message"].lower()
    assert ("name and phone" in reminder) or ("نام اور فون" in r["message"])

    await db_session.refresh(convo)
    assert _state(convo) == before
    # Emphatically NOT stored as the customer's name.
    assert convo.customer_name is None


async def test_picture_request_is_not_stored_as_the_address(client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100201"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    await _msg(client, s.id, "Ali Khan, 03001234567", cust)
    await db_session.refresh(convo)
    assert convo.order_stage == "CUSTOMER_DETAILS_REQUIRED"
    before = _state(convo)

    r = await _msg(client, s.id, "Send me the picture", cust)
    assert r["intent"] == "picture_request"
    assert r["image_url"]
    assert "address" in r["message"].lower()

    await db_session.refresh(convo)
    assert _state(convo) == before
    assert convo.customer_address is None


async def test_picture_request_does_not_change_the_payment_method(client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100202"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    await _msg(client, s.id, "Ali Khan, 03001234567", cust)
    await _msg(client, s.id, "House 4, Gulberg Lahore", cust)
    await db_session.refresh(convo)
    assert convo.order_stage == "ADDRESS_REQUIRED"
    before = _state(convo)

    r = await _msg(client, s.id, "Send me the picture", cust)
    assert r["intent"] == "picture_request"
    assert r["image_url"]

    await db_session.refresh(convo)
    assert _state(convo) == before
    assert convo.payment_method is None


async def test_a_product_with_no_picture_says_so_honestly(client, db_session):
    """Never "I'll send it shortly" — there is nothing to send."""
    s, p = await _shop(db_session, image=None)
    cust = "923001100203"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)

    r = await _msg(client, s.id, "Send me the picture", cust)
    assert r["image_url"] is None
    assert "no picture" in r["message"].lower()
    # Still tells them what the order needs, and still does not advance.
    assert "name and phone" in r["message"].lower()
    await db_session.refresh(convo)
    assert convo.order_stage == "QUANTITY_SELECTED"


# --- Other questions asked mid-checkout ------------------------------------

async def test_price_question_during_checkout_answers_from_the_database(client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100204"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    before = _state(convo)

    r = await _msg(client, s.id, "What is the price?", cust)
    assert r["intent"] == "price_query"
    assert "2,500" in r["message"]
    assert "name and phone" in r["message"].lower()

    await db_session.refresh(convo)
    assert _state(convo) == before


async def test_stock_question_during_checkout_answers_truthfully(client, db_session):
    s, p = await _shop(db_session, stock=7)
    cust = "923001100205"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    before = _state(convo)

    r = await _msg(client, s.id, "Is it in stock?", cust)
    assert r["intent"] == "stock_query"
    assert "7" in r["message"]

    await db_session.refresh(convo)
    assert _state(convo) == before


class _SaysSizeQuery(MockAIProvider):
    """Reproduces the live model on "What sizes do you have?".

    The regex table scores that phrase unknown 0.0, so without a stub this test
    would silently exercise the deterministic path instead of the routing it is
    meant to cover.
    """

    async def classify_intent(self, message, store_language, expected_order_field=None):
        result = await super().classify_intent(message, store_language, expected_order_field)
        if result is not None and "size" in message.lower():
            result.intent = "size_query"
            result.confidence = 0.95
            result.expected_field_valid = False
        return result


async def test_size_question_names_the_real_variant(client, db_session, monkeypatch):
    s, p = await _shop(db_session, size="M")
    cust = "923001100206"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    before = _state(convo)

    monkeypatch.setattr(cc, "get_ai_provider", lambda: _SaysSizeQuery())
    r = await _msg(client, s.id, "What sizes do you have?", cust)
    assert r["intent"] == "size_query"
    assert "M" in r["message"]

    await db_session.refresh(convo)
    assert _state(convo) == before


# --- Answers must still be consumed ----------------------------------------

async def test_valid_name_and_phone_advances_exactly_one_stage(client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100207"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)

    await _msg(client, s.id, "Ali Khan, 03001234567", cust)
    await db_session.refresh(convo)
    assert convo.order_stage == "CUSTOMER_DETAILS_REQUIRED"
    assert convo.customer_name == "Ali Khan"
    assert convo.customer_phone == "03001234567"


async def test_phone_without_a_name_keeps_the_phone_and_asks_only_for_the_name(
        client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100208"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)

    r = await _msg(client, s.id, "My number is 03001234567", cust)
    await db_session.refresh(convo)
    # Did not advance, did not store the sentence as a name…
    assert convo.order_stage == "QUANTITY_SELECTED"
    assert convo.customer_name is None
    # …but kept what they actually gave us, and asked only for what is missing.
    assert convo.customer_phone == "03001234567"
    assert "name" in r["message"].lower()

    # A bare name now completes the pair against the stored number.
    await _msg(client, s.id, "Ali Khan", cust)
    await db_session.refresh(convo)
    assert convo.order_stage == "CUSTOMER_DETAILS_REQUIRED"
    assert convo.customer_name == "Ali Khan"
    assert convo.customer_phone == "03001234567"


@pytest.mark.parametrize("refusal", [
    "I dont want to provide my name",
    "naam nahi dena",
])
async def test_a_refusal_is_acknowledged_not_stored_as_a_name(client, db_session, refusal):
    s, p = await _shop(db_session)
    cust = f"9230012{abs(hash(refusal)) % 10000:04d}"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)

    r = await _msg(client, s.id, refusal, cust)
    await db_session.refresh(convo)
    assert convo.customer_name is None
    assert convo.order_stage == "QUANTITY_SELECTED"
    # Acknowledges the refusal and offers a way out rather than repeating itself.
    assert r["message"] != "Please provide your name and phone number for the order."
    assert "agent" in r["message"].lower() or "نمائندے" in r["message"]


async def test_an_unrelated_reply_is_not_the_same_prompt_again(client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100209"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)

    r = await _msg(client, s.id, "I dont understand", cust)
    await db_session.refresh(convo)
    assert convo.customer_name is None
    # Shows the format that works instead of restating the identical sentence.
    assert "03001234567" in r["message"]


# --- Precedence ------------------------------------------------------------

async def test_cancellation_still_outranks_an_interrupt(client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100210"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)

    r = await _msg(client, s.id, "cancel my order", cust)
    assert r["intent"] == "order_cancel"
    await db_session.refresh(convo)
    assert convo.order_stage in ("BROWSING", "ORDER_CREATED")


async def test_human_agent_request_mid_order_still_escalates(client, db_session):
    s, p = await _shop(db_session)
    cust = "923001100211"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    before = _state(convo)

    r = await _msg(client, s.id, "talk to a human agent", cust)
    assert r["needs_human"] is True
    # The catalogue-search miss must not reach the customer here.
    assert "catalogue" not in r["message"].lower()

    await db_session.refresh(convo)
    assert _state(convo) == before


# --- The LLM may understand; the database owns the facts -------------------

class _LyingProvider(MockAIProvider):
    """Classifies correctly but tries to substitute invented product facts."""

    async def classify_intent(self, message, store_language, expected_order_field=None):
        result = await super().classify_intent(message, store_language, expected_order_field)
        if result is not None:
            result.intent = "picture_request"
            result.confidence = 1.0
        return result

    async def generate_response(self, context):
        response = await super().generate_response(context)
        response.message = "Here it is: http://evil.example/fake.jpg — price PKR 99"
        response.image_url = "http://evil.example/fake.jpg"
        return response


async def test_the_model_cannot_substitute_the_image_url_or_price(
        client, db_session, monkeypatch):
    s, p = await _shop(db_session)
    cust = "923001100212"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)

    monkeypatch.setattr(cc, "get_ai_provider", lambda: _LyingProvider())
    r = await _msg(client, s.id, "Send me the picture", cust)

    # The URL is the seller's persisted image, never the model's.
    assert r["image_url"] == resolve_media_url("/uploads/kurta.jpg")
    assert "evil.example" not in str(r["image_url"])
    assert "evil.example" not in r["message"]
    assert "PKR 99" not in r["message"]
    assert "PKR 2,500" in r["message"]


class _BrokenProvider(MockAIProvider):
    """Every model call fails — the deterministic path must still work."""

    async def classify_intent(self, message, store_language, expected_order_field=None):
        raise RuntimeError("model unavailable")


async def test_a_model_outage_falls_back_to_deterministic_routing(
        client, db_session, monkeypatch):
    s, p = await _shop(db_session)
    cust = "923001100213"
    convo = await _at_customer_details(client, db_session, s.id, p, cust)
    before = _state(convo)

    monkeypatch.setattr(cc, "get_ai_provider", lambda: _BrokenProvider())
    r = await _msg(client, s.id, "Send me the picture", cust)

    # Deterministic detection alone still routes the interrupt correctly.
    assert r["intent"] == "picture_request"
    assert r["image_url"] == resolve_media_url("/uploads/kurta.jpg")
    await db_session.refresh(convo)
    assert _state(convo) == before
