"""Tests for WhatsApp QR code generation and synchronization flow."""
import os
os.environ["AI_PROVIDER"] = "mock"

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport, TimeoutException
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import init_db, create_tables, drop_tables
from app.models.store import Store
from app.models.whatsapp import WhatsAppSession


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def qr_db_engine():
    engine, factory = init_db("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    yield engine, factory
    await drop_tables(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(qr_db_engine):
    engine, factory = qr_db_engine
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(qr_db_engine):
    from app.main import app
    from app.database import get_db
    engine, factory = qr_db_engine

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def store(db_session: AsyncSession):
    """Get or create a test store."""
    result = await db_session.execute(
        select(Store).where(Store.id == "test-qr-store")
    )
    s = result.scalar_one_or_none()
    if not s:
        s = Store(
            id="test-qr-store",
            business_name="QR Test Store",
            owner_name="Test",
            preferred_language="english",
            ai_enabled=True,
        )
        db_session.add(s)
        await db_session.commit()
    # Clean up any existing sessions
    existing = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    for sess in existing.scalars().all():
        await db_session.delete(sess)
    await db_session.commit()
    return s


def _make_response(status_code, json_data):
    """Create an httpx Response with a request set."""
    resp = httpx.Response(status_code, json=json_data)
    resp._request = httpx.Request("POST", "http://test")
    return resp


# ── Test: QR returned directly by connect ─────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_returns_qr_directly(async_client: AsyncClient, store, db_session):
    """When gateway returns QR immediately, it should be persisted in DB."""
    mock_response = _make_response(200, {
        "status": "initializing",
        "storeId": "test-qr-store",
        "qr_code": "data:image/png;base64,FAKE_QR_DATA",
    })
    
    with patch("app.routers.whatsapp.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance
        
        resp = await async_client.post(
            "/api/stores/test-qr-store/whatsapp/connect",
        )
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "waiting_for_qr"
    assert data["qr_code"] == "data:image/png;base64,FAKE_QR_DATA"
    
    # Verify persisted in DB
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    session = result.scalar_one()
    assert session.qr_code == "data:image/png;base64,FAKE_QR_DATA"
    assert session.status == "waiting_for_qr"


# ── Test: QR received via webhook ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qr_received_via_session_event(async_client: AsyncClient, store, db_session):
    """QR sent by gateway webhook should be persisted in DB."""
    # Create initial session
    s = WhatsAppSession(store_id="test-qr-store", status="initializing")
    db_session.add(s)
    await db_session.commit()

    resp = await async_client.post(
        "/internal/whatsapp/session-events",
        json={
            "store_id": "test-qr-store",
            "status": "waiting_for_qr",
            "qr_code": "data:image/png;base64,WEBHOOK_QR_DATA",
        },
        headers={"X-Internal-Token": "dev-internal-token"},
    )
    
    assert resp.status_code == 200
    
    # Verify persisted
    db_session.expire_all()
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    session = result.scalar_one()
    assert session.qr_code == "data:image/png;base64,WEBHOOK_QR_DATA"
    assert session.status == "waiting_for_qr"


# ── Test: Gateway timeout → failed ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_gateway_timeout_sets_failed(async_client: AsyncClient, store, db_session):
    """Gateway timeout should set status to failed."""
    with patch("app.routers.whatsapp.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = TimeoutException("timed out")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance
        
        resp = await async_client.post(
            "/api/stores/test-qr-store/whatsapp/connect",
        )
    
    assert resp.status_code == 504
    
    # Verify DB status
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    session = result.scalar_one()
    assert session.status == "failed"


# ── Test: Gateway error → failed ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gateway_error_sets_failed(async_client: AsyncClient, store, db_session):
    """Gateway HTTP error should set status to failed."""
    with patch("app.routers.whatsapp.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.side_effect = Exception("Connection refused")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance
        
        resp = await async_client.post(
            "/api/stores/test-qr-store/whatsapp/connect",
        )
    
    assert resp.status_code == 502
    
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    session = result.scalar_one()
    assert session.status == "failed"


# ── Test: Status endpoint returns DB QR ───────────────────────────────────────

@pytest.mark.asyncio
async def test_status_returns_db_qr(async_client: AsyncClient, store, db_session):
    """Status endpoint should return QR from DB."""
    s = WhatsAppSession(
        store_id="test-qr-store",
        status="waiting_for_qr",
        qr_code="data:image/png;base64,DB_QR",
    )
    db_session.add(s)
    await db_session.commit()

    # Mock gateway to return nothing (simulating restart/cache loss)
    with patch("app.routers.whatsapp.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_response = _make_response(404, {"error": "QR not available"})
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance
        
        resp = await async_client.get(
            "/api/stores/test-qr-store/whatsapp/status",
        )
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["qr_code"] == "data:image/png;base64,DB_QR"
    assert data["status"] == "waiting_for_qr"


# ── Test: Connected clears QR ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connected_clears_qr(async_client: AsyncClient, store, db_session):
    """When status changes to connected, QR should be cleared."""
    s = WhatsAppSession(
        store_id="test-qr-store",
        status="waiting_for_qr",
        qr_code="data:image/png;base64,OLD_QR",
    )
    db_session.add(s)
    await db_session.commit()

    resp = await async_client.post(
        "/internal/whatsapp/session-events",
        json={
            "store_id": "test-qr-store",
            "status": "connected",
            "phone_number": "923001234567",
        },
        headers={"X-Internal-Token": "dev-internal-token"},
    )
    
    assert resp.status_code == 200
    
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    session = result.scalar_one()
    assert session.qr_code is None
    assert session.status == "connected"
    assert session.phone_number == "923001234567"
    assert session.last_connected_at is not None


# ── Test: Disconnect clears QR ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disconnect_clears_qr(async_client: AsyncClient, store, db_session):
    """Disconnect should clear QR and set status."""
    s = WhatsAppSession(
        store_id="test-qr-store",
        status="connected",
        qr_code=None,
        phone_number="923001234567",
    )
    db_session.add(s)
    await db_session.commit()

    with patch("app.routers.whatsapp.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.delete.return_value = _make_response(200, {"status": "disconnected"})
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance
        
        resp = await async_client.delete(
            "/api/stores/test-qr-store/whatsapp",
        )
    
    assert resp.status_code == 200
    
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    session = result.scalar_one()
    assert session.status == "disconnected"
    assert session.qr_code is None


# ── Test: Stale initializing recovery ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_initializing_recovery(async_client: AsyncClient, store, db_session):
    """Sessions stuck in initializing beyond threshold should be marked failed."""
    s = WhatsAppSession(
        store_id="test-qr-store",
        status="initializing",
        updated_at=datetime.utcnow() - timedelta(seconds=300),  # 5 min old
    )
    db_session.add(s)
    await db_session.commit()

    # Mock gateway (will fail since we're testing stale recovery)
    with patch("app.routers.whatsapp.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = Exception("gateway down")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance
        
        resp = await async_client.get(
            "/api/stores/test-qr-store/whatsapp/status",
        )
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"


# ── Test: Repeated connect is idempotent ──────────────────────────────────────

@pytest.mark.asyncio
async def test_repeated_connect_idempotent(async_client: AsyncClient, store, db_session):
    """Calling connect twice should not create duplicate sessions."""
    mock_response = _make_response(200, {
        "status": "initializing",
        "storeId": "test-qr-store",
        "qr_code": "data:image/png;base64,QR_1",
    })
    
    with patch("app.routers.whatsapp.httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_instance
        
        # First connect
        await async_client.post("/api/stores/test-qr-store/whatsapp/connect")
        
        # Second connect with new QR
        mock_response2 = _make_response(200, {
            "status": "initializing",
            "storeId": "test-qr-store",
            "qr_code": "data:image/png;base64,QR_2",
        })
        mock_instance.post.return_value = mock_response2
        
        resp = await async_client.post("/api/stores/test-qr-store/whatsapp/connect")
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["qr_code"] == "data:image/png;base64,QR_2"
    
    # Should still be only one session
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    sessions = result.scalars().all()
    assert len(sessions) == 1
    assert sessions[0].qr_code == "data:image/png;base64,QR_2"


# ── Test: Session event without token is rejected ─────────────────────────────

@pytest.mark.asyncio
async def test_session_event_requires_token(async_client: AsyncClient, store):
    """Session events without valid token should be rejected."""
    resp = await async_client.post(
        "/internal/whatsapp/session-events",
        json={
            "store_id": "test-qr-store",
            "status": "connected",
        },
    )
    assert resp.status_code == 401


# ── Test: Failed status clears QR via webhook ─────────────────────────────────

@pytest.mark.asyncio
async def test_failed_status_clears_qr(async_client: AsyncClient, store, db_session):
    """When gateway reports failed, QR should be cleared."""
    s = WhatsAppSession(
        store_id="test-qr-store",
        status="waiting_for_qr",
        qr_code="data:image/png;base64,STALE_QR",
    )
    db_session.add(s)
    await db_session.commit()

    resp = await async_client.post(
        "/internal/whatsapp/session-events",
        json={
            "store_id": "test-qr-store",
            "status": "failed",
            "error": "WhatsApp disconnected",
        },
        headers={"X-Internal-Token": "dev-internal-token"},
    )
    
    assert resp.status_code == 200
    
    db_session.expire_all()
    result = await db_session.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == "test-qr-store")
    )
    session = result.scalar_one()
    assert session.qr_code is None
    assert session.status == "failed"
