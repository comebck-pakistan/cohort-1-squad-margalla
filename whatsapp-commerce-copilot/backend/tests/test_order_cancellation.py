"""Cancelling an order must release its stock back to the catalogue.

Confirming an order decrements stock; before this, cancelling marked the order
cancelled but kept the units reserved forever, so the seller silently lost
sellable inventory on every cancellation.

Also covers the fabricated-confirmation guard: the AI must never tell a customer
their order is placed, because only the state machine can create one (and that
path names a real order ID). A fabricated confirmation leaves the customer
believing they bought something the seller never sees — and no stock moves.
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
from app.services.ai_provider import MockAIProvider, AIResponseSchema
import app.services.conversation_controller as cc

pytestmark = pytest.mark.asyncio
TOKEN = {"X-Internal-Token": "dev-internal-token"}
START_STOCK = 6


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


async def _seed(db, name="Cancel Store"):
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
    v = ProductVariant(product_id=p.id, price=3500, stock=START_STOCK,
                       color="white", size="medium", is_active=True)
    db.add(v)
    await db.flush()
    await db.commit()
    return s, p, v


async def _msg(client, sid, text, customer):
    r = await client.post("/internal/whatsapp/messages",
                          json={"store_id": sid, "customer_number": customer, "message": text},
                          headers=TOKEN)
    assert r.status_code == 200, r.text
    return r.json()


async def _stock(db, vid):
    v = (await db.execute(
        select(ProductVariant).where(ProductVariant.id == vid))).scalar_one()
    await db.refresh(v)
    return v.stock


async def _place_order(client, sid, cust, qty="2"):
    await _msg(client, sid, "Hi", cust)
    await _msg(client, sid, "1", cust)
    await _msg(client, sid, "1", cust)
    await _msg(client, sid, "Order", cust)
    await _msg(client, sid, "white medium", cust)
    await _msg(client, sid, qty, cust)
    await _msg(client, sid, "Ali Khan 03001234567", cust)
    await _msg(client, sid, "House 12, Gulberg, Lahore", cust)
    await _msg(client, sid, "COD", cust)
    await _msg(client, sid, "haan", cust)


async def test_cancelling_an_order_restores_the_stock(client, db_session):
    s, _, v = await _seed(db_session)
    cust = "923004440001"

    await _place_order(client, s.id, cust, qty="2")
    assert await _stock(db_session, v.id) == START_STOCK - 2

    r = await _msg(client, s.id, "cancel my order", cust)
    assert r["intent"] == "order_cancel"

    order = (await db_session.execute(
        select(Order).where(Order.store_id == s.id))).scalars().one()
    assert order.status == "cancelled"
    assert await _stock(db_session, v.id) == START_STOCK, "stock was not released"
    assert order.id in r["message"], "customer should be told which order was cancelled"


async def test_cancelling_twice_does_not_restock_twice(client, db_session):
    s, _, v = await _seed(db_session, name="Double Cancel")
    cust = "923004440002"

    await _place_order(client, s.id, cust, qty="2")
    await _msg(client, s.id, "cancel my order", cust)
    assert await _stock(db_session, v.id) == START_STOCK

    await _msg(client, s.id, "cancel order", cust)
    assert await _stock(db_session, v.id) == START_STOCK, "stock inflated by a repeat cancel"


async def test_cancel_before_any_order_exists_is_safe(client, db_session):
    """Cancelling mid-funnel must not touch stock or invent an order."""
    s, _, v = await _seed(db_session, name="Early Cancel")
    cust = "923004440003"

    await _msg(client, s.id, "Hi", cust)
    await _msg(client, s.id, "1", cust)
    await _msg(client, s.id, "1", cust)
    await _msg(client, s.id, "Order", cust)
    await _msg(client, s.id, "cancel", cust)

    assert await _stock(db_session, v.id) == START_STOCK
    orders = (await db_session.execute(
        select(Order).where(Order.store_id == s.id))).scalars().all()
    assert orders == []


async def test_stock_is_released_only_for_the_cancelled_order(client, db_session):
    """A second live order keeps its reservation when the first is cancelled."""
    s, _, v = await _seed(db_session, name="Two Orders")
    c1, c2 = "923004440004", "923004440005"

    await _place_order(client, s.id, c1, qty="2")
    await _place_order(client, s.id, c2, qty="1")
    assert await _stock(db_session, v.id) == START_STOCK - 3

    await _msg(client, s.id, "cancel my order", c1)
    # only c1's two units come back; c2's single unit stays reserved
    assert await _stock(db_session, v.id) == START_STOCK - 1


class FabricatingProvider(MockAIProvider):
    """An LLM that invents a confirmation, as seen live on WhatsApp."""

    def name(self) -> str:
        return "fabricator"

    def is_configured(self) -> bool:
        return True

    async def process(self, context) -> AIResponseSchema:
        return AIResponseSchema(
            response_message=(
                "Your order for the *Red Dress* in size *Medium* has been "
                "successfully confirmed with Cash on Delivery! 🎉🚚"
            ),
            confidence=0.9,
        )


async def test_ai_cannot_fabricate_an_order_confirmation(client, db_session, monkeypatch):
    """The bot must never claim an order exists when none was created."""
    monkeypatch.setattr(cc, "get_ai_provider", lambda: FabricatingProvider())
    s, _, v = await _seed(db_session, name="Fabricator Store")
    cust = "923004440006"

    # a vague message routes through the AI phrasing path
    r = await _msg(client, s.id, "hmm what about that thing", cust)

    assert "successfully confirmed" not in r["message"].lower()
    orders = (await db_session.execute(
        select(Order).where(Order.store_id == s.id))).scalars().all()
    assert orders == [], "no order was created, so none may be claimed"
    assert await _stock(db_session, v.id) == START_STOCK
