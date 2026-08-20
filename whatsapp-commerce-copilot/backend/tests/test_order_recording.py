"""Orders must actually be recorded when the customer confirms.

Regression for the live bug: orders never appeared in the dashboard. The mock AI
provider mirrors the deterministic detector, so the suite never exercised the
LLM-override path. A real LLM labels "haan"/"yes" as `acknowledgement` (a known
intent, confidence ~0.9) which outranks the deterministic `order_confirmation`
(0.7) and overrides it — so the funnel sat at ORDER_CONFIRMATION forever,
re-asking "confirm or cancel?" and never writing the Order row.

These tests drive the controller with a stub provider that behaves like the live
LLM. Isolated engine + get_db override (same pattern as test_shop_flow).
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
from app.models.order import Order
from app.models.conversation import Conversation
from app.services.ai_provider import MockAIProvider, AIIntentSchema
import app.services.conversation_controller as cc

pytestmark = pytest.mark.asyncio
TOKEN = {"X-Internal-Token": "dev-internal-token"}

# Affirmatives a real LLM tends to label as a bare acknowledgement.
_AFFIRMATIVE = {"haan", "han", "ji", "yes", "ok", "okay", "theek", "acha",
                "haan confirm", "ji haan", "yes please", "👍"}


class AckHappyProvider(MockAIProvider):
    """Mimics the live LLM: calls affirmatives `acknowledgement` @0.9."""

    async def classify_intent(self, message: str, store_language: str):
        base = await super().classify_intent(message, store_language)
        if message.strip().lower() in _AFFIRMATIVE:
            return AIIntentSchema(
                intent="acknowledgement", confidence=0.9,
                input_language=base.input_language,
                response_language=base.response_language,
                language_confidence=base.language_confidence,
            )
        return base


@pytest.fixture(autouse=True)
def live_like_llm(monkeypatch):
    provider = AckHappyProvider()
    monkeypatch.setattr(cc, "get_ai_provider", lambda: provider)


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


async def _seed(db, name="Noor Fashion"):
    s = Store(business_name=name, owner_name="O", preferred_language="en")
    db.add(s)
    await db.flush()
    c = Category(store_id=s.id, name="Lawn", display_order=1, is_active=True)
    db.add(c)
    await db.flush()
    p = Product(store_id=s.id, name="Printed Lawn Suit", category_id=c.id,
                base_price=3500, is_active=True)
    db.add(p)
    await db.flush()
    db.add(ProductVariant(product_id=p.id, price=3500, stock=6,
                          color="white", size="medium", is_active=True))
    await db.flush()
    await db.commit()
    return s, p


async def _msg(client, sid, text, customer):
    r = await client.post("/internal/whatsapp/messages",
                          json={"store_id": sid, "customer_number": customer, "message": text},
                          headers=TOKEN)
    assert r.status_code == 200, r.text
    return r.json()


async def _walk_to_confirmation(client, sid, cust):
    """Drive the funnel up to the order summary / confirmation step."""
    await _msg(client, sid, "Hi", cust)
    await _msg(client, sid, "1", cust)               # open Lawn
    await _msg(client, sid, "1", cust)               # pick the product
    await _msg(client, sid, "Order", cust)
    await _msg(client, sid, "white medium", cust)
    await _msg(client, sid, "2", cust)               # quantity
    await _msg(client, sid, "Ali Khan 03001234567", cust)
    await _msg(client, sid, "House 12, Gulberg, Lahore", cust)
    await _msg(client, sid, "COD", cust)


async def _stage(db, sid):
    conv = (await db.execute(
        select(Conversation).where(Conversation.store_id == sid))).scalars().first()
    return conv.order_stage if conv else None


@pytest.mark.parametrize("affirmative", [
    "haan", "yes", "ji", "ok", "haan confirm", "👍",
    # The live bot replies in Urdu script, so customers answer in it. These are
    # not in the regex intent table at all (they classify as unknown 0.0), which
    # left the LLM's label entirely in charge of whether an order got recorded.
    "ہاں", "جی ہاں", "ٹھیک ہے", "کنفرم کریں",
])
async def test_affirmative_records_the_order(client, db_session, affirmative):
    """Every natural yes must write the Order row, not loop on 'confirm or cancel'."""
    s, prod = await _seed(db_session)
    cust = "9230012" + str(abs(hash(affirmative)) % 10000).zfill(4)

    await _walk_to_confirmation(client, s.id, cust)
    assert await _stage(db_session, s.id) == "ORDER_CONFIRMATION"

    await _msg(client, s.id, affirmative, cust)

    orders = (await db_session.execute(
        select(Order).where(Order.store_id == s.id))).scalars().all()
    assert len(orders) == 1, f"{affirmative!r} did not record an order"
    assert orders[0].customer_name == "Ali Khan"
    assert orders[0].payment_method == "COD"
    assert orders[0].total_amount == 7000  # 3500 x 2

    # and it is visible through the dashboard's orders endpoint
    r = await client.get(f"/api/stores/{s.id}/orders")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["items"][0]["product_name"] == "Printed Lawn Suit"
    assert body[0]["items"][0]["quantity"] == 2


async def test_negative_still_cancels_and_records_nothing(client, db_session):
    """The no-path must keep working — no order written."""
    s, _ = await _seed(db_session, name="Cancel Store")
    cust = "923009998888"
    await _walk_to_confirmation(client, s.id, cust)
    await _msg(client, s.id, "nahi", cust)

    orders = (await db_session.execute(
        select(Order).where(Order.store_id == s.id))).scalars().all()
    assert orders == []


async def test_acknowledgement_outside_order_flow_is_not_an_order(client, db_session):
    """A bare 'ok' while browsing must never create an order."""
    s, _ = await _seed(db_session, name="Browse Store")
    cust = "923009997777"
    await _msg(client, s.id, "Hi", cust)
    await _msg(client, s.id, "1", cust)
    await _msg(client, s.id, "1", cust)   # viewing a product, no order started
    await _msg(client, s.id, "ok", cust)
    await _msg(client, s.id, "haan", cust)

    orders = (await db_session.execute(
        select(Order).where(Order.store_id == s.id))).scalars().all()
    assert orders == [], "affirmative while browsing must not create an order"
