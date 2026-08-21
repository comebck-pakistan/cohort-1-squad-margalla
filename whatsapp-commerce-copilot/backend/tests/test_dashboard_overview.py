"""Read-only dashboard overview endpoint.

Covers store scoping, revenue rules, date-boundary handling, phone masking and
activity ordering. Isolated engine + get_db override so committed rows never
leak into the shared conftest engine.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import get_engine, get_session_factory, create_tables, drop_tables, get_db
from app.models.store import Store
from app.models.customer import Customer
from app.models.conversation import Conversation, Message
from app.models.handoff import HumanHandoff
from app.models.order import Order, OrderItem
from app.routers.dashboard import BUSINESS_TZ

pytestmark = pytest.mark.asyncio
URL = "/api/stores/{sid}/dashboard/overview"


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


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def _store(db, name="Noor"):
    s = Store(business_name=name, owner_name="O", preferred_language="en")
    db.add(s)
    await db.flush()
    return s


async def _conversation(db, store, phone="923001234567", created=None):
    c = Customer(store_id=store.id, phone_number=phone)
    db.add(c)
    await db.flush()
    conv = Conversation(store_id=store.id, customer_id=c.id)
    if created:
        conv.created_at = created
    db.add(conv)
    await db.flush()
    return conv


async def _order(db, store, conv, total=1000.0, status="pending",
                 created=None, updated=None, product="Lawn Suit", qty=1):
    o = Order(store_id=store.id, conversation_id=conv.id, customer_id=conv.customer_id,
              status=status, total_amount=total)
    if created:
        o.created_at = created
    if updated:
        o.updated_at = updated
    o.items = [OrderItem(product_id="p1", variant_id="v1", product_name=product,
                         variant_description="white medium", quantity=qty, unit_price=total)]
    db.add(o)
    await db.flush()
    return o


async def _inbound(db, conv, content="hello", created=None):
    m = Message(conversation_id=conv.id, direction="inbound", content=content)
    if created:
        m.created_at = created
    db.add(m)
    await db.flush()
    return m


async def _handoff(db, store, conv, status="pending", reason="complaint", created=None):
    h = HumanHandoff(store_id=store.id, conversation_id=conv.id,
                     reason=reason, summary="needs a human", status=status)
    if created:
        h.created_at = created
    db.add(h)
    await db.flush()
    return h


async def _get(client, sid, **params):
    r = await client.get(URL.format(sid=sid), params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def test_empty_store_returns_zeros_and_empty_lists(client, db_session):
    s = await _store(db_session, "Empty")
    await db_session.commit()
    body = await _get(client, s.id)
    assert body["metrics"] == {
        "conversations_handled": 0, "inbound_messages": 0,
        "orders_confirmed": 0, "orders_cancelled": 0,
        "revenue_pkr": 0.0, "needs_attention": 0,
    }
    assert body["activity"] == []
    assert body["attention_items"] == []
    assert body["period"]["timezone"] == "Asia/Karachi"
    assert body["period"]["range"] == "7d"          # default


async def test_metrics_come_from_persisted_rows(client, db_session):
    s = await _store(db_session, "Metrics")
    conv = await _conversation(db_session, s)
    await _inbound(db_session, conv)
    await _inbound(db_session, conv)
    await _order(db_session, s, conv, total=4500)
    await _order(db_session, s, conv, total=3200)
    await _handoff(db_session, s, conv)
    await db_session.commit()

    m = (await _get(client, s.id))["metrics"]
    assert m["conversations_handled"] == 1      # distinct conversations
    assert m["inbound_messages"] == 2
    assert m["orders_confirmed"] == 2
    assert m["revenue_pkr"] == 7700.0           # persisted totals
    assert m["needs_attention"] == 1


async def test_cancelled_orders_excluded_from_revenue_and_count(client, db_session):
    s = await _store(db_session, "Cancels")
    conv = await _conversation(db_session, s)
    await _order(db_session, s, conv, total=5000)
    await _order(db_session, s, conv, total=9999, status="cancelled")
    await db_session.commit()

    m = (await _get(client, s.id))["metrics"]
    assert m["orders_confirmed"] == 1
    assert m["revenue_pkr"] == 5000.0, "cancelled order must not add revenue"
    assert m["orders_cancelled"] == 1


async def test_every_metric_is_scoped_by_store(client, db_session):
    a = await _store(db_session, "StoreA")
    b = await _store(db_session, "StoreB")
    ca = await _conversation(db_session, a, phone="923001110000")
    cb = await _conversation(db_session, b, phone="923002220000")
    await _inbound(db_session, ca)
    await _order(db_session, a, ca, total=1000)
    await _handoff(db_session, a, ca)
    # store B has much more activity
    for _ in range(3):
        await _inbound(db_session, cb)
        await _order(db_session, b, cb, total=8000)
        await _handoff(db_session, b, cb)
    await db_session.commit()

    ma = (await _get(client, a.id))["metrics"]
    assert ma["orders_confirmed"] == 1 and ma["revenue_pkr"] == 1000.0
    assert ma["conversations_handled"] == 1 and ma["needs_attention"] == 1

    mb = (await _get(client, b.id))["metrics"]
    assert mb["orders_confirmed"] == 3 and mb["revenue_pkr"] == 24000.0


async def test_cross_store_records_never_appear_in_lists(client, db_session):
    a = await _store(db_session, "ListA")
    b = await _store(db_session, "ListB")
    ca = await _conversation(db_session, a, phone="923001110001")
    cb = await _conversation(db_session, b, phone="923002220002")
    await _order(db_session, a, ca, product="A Suit")
    await _order(db_session, b, cb, product="B Sneakers")
    await _handoff(db_session, a, ca, reason="complaint")
    await _handoff(db_session, b, cb, reason="refund")
    await db_session.commit()

    body = await _get(client, a.id)
    blob = str(body)
    assert "A Suit" in blob
    assert "B Sneakers" not in blob
    assert all(i["conversation_id"] == ca.id for i in body["attention_items"])


async def test_only_unresolved_handoffs_are_listed(client, db_session):
    s = await _store(db_session, "Handoffs")
    conv = await _conversation(db_session, s)
    await _handoff(db_session, s, conv, status="pending")
    await _handoff(db_session, s, conv, status="active")
    await _handoff(db_session, s, conv, status="resolved")
    await db_session.commit()

    body = await _get(client, s.id)
    assert body["metrics"]["needs_attention"] == 2, "resolved must not count"
    statuses = {i["status"] for i in body["attention_items"]}
    assert statuses == {"pending", "active"}
    # the count must agree with the list it is shown next to
    assert body["metrics"]["needs_attention"] == len(body["attention_items"])


async def test_phone_numbers_are_masked(client, db_session):
    s = await _store(db_session, "Privacy")
    conv = await _conversation(db_session, s, phone="923009876543")
    await _handoff(db_session, s, conv)
    await db_session.commit()

    body = await _get(client, s.id)
    assert "923009876543" not in str(body), "raw customer number leaked"
    assert body["attention_items"][0]["customer_phone_masked"] == "+92 300 XXXXXXX"


async def test_activity_is_newest_first(client, db_session):
    s = await _store(db_session, "Ordering")
    now = _utcnow_naive()
    conv = await _conversation(db_session, s, created=now - timedelta(hours=5))
    await _order(db_session, s, conv, product="Older Suit", created=now - timedelta(hours=3))
    await _order(db_session, s, conv, product="Newer Suit", created=now - timedelta(minutes=10))
    await _handoff(db_session, s, conv, created=now - timedelta(hours=1))
    await db_session.commit()

    activity = (await _get(client, s.id))["activity"]
    stamps = [i["created_at"] for i in activity]
    assert stamps == sorted(stamps, reverse=True)
    assert "Newer Suit" in activity[0]["description"]
    assert {"order_confirmed", "escalation", "conversation_started"} >= {i["type"] for i in activity}


async def test_activity_limit_is_respected(client, db_session):
    s = await _store(db_session, "Limit")
    conv = await _conversation(db_session, s)
    for i in range(8):
        await _order(db_session, s, conv, product=f"Suit {i}")
    await db_session.commit()

    assert len((await _get(client, s.id, activity_limit=3))["activity"]) == 3


async def test_date_presets_use_correct_boundaries(client, db_session):
    """A row from three days ago is inside 7d/30d but outside today/yesterday."""
    s = await _store(db_session, "Boundaries")
    now_local = datetime.now(BUSINESS_TZ)
    three_days_ago_utc = (now_local - timedelta(days=3)).astimezone(timezone.utc).replace(tzinfo=None)
    conv = await _conversation(db_session, s, created=three_days_ago_utc)
    await _order(db_session, s, conv, total=2500, created=three_days_ago_utc)
    await db_session.commit()

    assert (await _get(client, s.id, range="7d"))["metrics"]["orders_confirmed"] == 1
    assert (await _get(client, s.id, range="30d"))["metrics"]["orders_confirmed"] == 1
    assert (await _get(client, s.id, range="all"))["metrics"]["orders_confirmed"] == 1
    assert (await _get(client, s.id, range="today"))["metrics"]["orders_confirmed"] == 0
    assert (await _get(client, s.id, range="yesterday"))["metrics"]["orders_confirmed"] == 0


async def test_today_range_includes_a_row_created_now(client, db_session):
    s = await _store(db_session, "Today")
    conv = await _conversation(db_session, s)
    await _order(db_session, s, conv, total=1500)
    await db_session.commit()
    body = await _get(client, s.id, range="today")
    assert body["metrics"]["orders_confirmed"] == 1
    assert body["period"]["range"] == "today"


async def test_custom_range_is_inclusive_of_the_end_date(client, db_session):
    s = await _store(db_session, "Custom")
    now_local = datetime.now(BUSINESS_TZ)
    today_local_date = now_local.date()
    conv = await _conversation(db_session, s)
    await _order(db_session, s, conv, total=777)
    await db_session.commit()

    body = await _get(client, s.id,
                      start_date=today_local_date.isoformat(),
                      end_date=today_local_date.isoformat())
    assert body["period"]["range"] == "custom"
    assert body["metrics"]["orders_confirmed"] == 1, "end date must be inclusive"


@pytest.mark.parametrize("params,expected", [
    ({"start_date": "2026-01-01"}, 400),                       # missing end
    ({"end_date": "2026-01-01"}, 400),                         # missing start
    ({"start_date": "not-a-date", "end_date": "2026-01-02"}, 400),
    ({"start_date": "2026-02-02", "end_date": "2026-01-01"}, 400),  # reversed
    ({"range": "last_century"}, 400),
])
async def test_invalid_date_input_is_rejected(client, db_session, params, expected):
    s = await _store(db_session, "Validation")
    await db_session.commit()
    r = await client.get(URL.format(sid=s.id), params=params)
    assert r.status_code == expected


async def test_unknown_store_is_404(client, db_session):
    r = await client.get(URL.format(sid="no-such-store"))
    assert r.status_code == 404


async def test_cancelled_order_appears_in_activity_as_cancellation(client, db_session):
    s = await _store(db_session, "CancelActivity")
    conv = await _conversation(db_session, s)
    await _order(db_session, s, conv, total=4500, status="cancelled", product="Returned Suit")
    await db_session.commit()

    activity = (await _get(client, s.id))["activity"]
    cancels = [i for i in activity if i["type"] == "order_cancelled"]
    assert len(cancels) == 1
    assert "Returned Suit" in cancels[0]["description"]
    # and it is not double-counted as a confirmed order
    assert not [i for i in activity if i["type"] == "order_confirmed"]


async def test_response_timestamps_are_timezone_aware(client, db_session):
    s = await _store(db_session, "Stamps")
    conv = await _conversation(db_session, s)
    await _order(db_session, s, conv)
    await _handoff(db_session, s, conv)
    await db_session.commit()

    body = await _get(client, s.id)
    for stamp in [body["generated_at"], body["period"]["start"], body["period"]["end"],
                  body["activity"][0]["created_at"], body["attention_items"][0]["created_at"]]:
        assert datetime.fromisoformat(stamp).tzinfo is not None


async def test_no_raw_message_bodies_are_returned(client, db_session):
    s = await _store(db_session, "NoBodies")
    conv = await _conversation(db_session, s)
    await _inbound(db_session, conv, content="my secret address is 12 Elm Street")
    await db_session.commit()
    assert "secret address" not in str(await _get(client, s.id))


async def test_long_handoff_summary_is_truncated(client, db_session):
    """Summaries embed the customer's own words; only a snippet is surfaced."""
    s = await _store(db_session, "Snippet")
    conv = await _conversation(db_session, s)
    h = await _handoff(db_session, s, conv)
    h.summary = "Customer: " + ("x" * 500)
    await db_session.commit()

    item = (await _get(client, s.id))["attention_items"][0]
    assert len(item["summary"]) <= 141
    assert item["summary"].endswith("…")
