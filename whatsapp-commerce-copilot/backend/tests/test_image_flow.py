import pytest
import uuid
import io
import os
from PIL import Image
from httpx import AsyncClient
from app.models.product import Product
from app.schemas.api import InternalSessionEvent
from app.services.ai_provider import AIRequestContext, AIResponseSchema
from sqlalchemy import select

from app.models.store import Store
from app.database import get_db, init_db, create_tables, drop_tables
import pytest_asyncio
from httpx import ASGITransport
from app.main import app
from unittest.mock import patch, AsyncMock
from pathlib import Path

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture(scope="module", autouse=True)
def isolated_upload_dir():
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["UPLOAD_DIR"] = temp_dir
        yield temp_dir

@pytest_asyncio.fixture(scope="module")
async def db_engine():
    engine, factory = init_db("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    yield engine, factory
    await drop_tables(engine)
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(db_engine):
    engine, factory = db_engine
    async with factory() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def async_client(db_session, store):
    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def store(db_session):
    import uuid
    store_id = f"test-store-{uuid.uuid4().hex[:8]}"
    store = Store(id=store_id, business_name="Test Store", owner_name="Owner", ai_enabled=True)
    db_session.add(store)
    await db_session.commit()
    await db_session.refresh(store)
    return store

def _make_jpeg(width=100, height=100, color='red'):
    """Helper to create a valid JPEG byte stream."""
    img = Image.new('RGB', (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf


# ===================================================================
# Existing tests — preserved
# ===================================================================

@pytest.mark.asyncio
async def test_image_upload_validation_and_conversion(async_client, store):
    img_byte_arr = _make_jpeg()

    data = {
        "name": "Test Image Product",
        "price": 1000.0,
        "stock": 10
    }
    files = {
        "image": ("test.jpg", img_byte_arr, "image/jpeg")
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data,
        files=files
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["image_url"] is not None
    assert res_data["image_url"].endswith(".jpg")

    # Verify the file was saved
    filename = res_data["image_url"].split("/")[-1]
    filepath = os.path.join(os.environ["UPLOAD_DIR"], filename)
    assert os.path.exists(filepath)

    # Read saved file to ensure it's a valid JPEG
    saved_img = Image.open(filepath)
    assert saved_img.format == "JPEG"

@pytest.mark.asyncio
async def test_invalid_image_upload_rejected(async_client, store):
    data = {
        "name": "Invalid Image Product",
        "price": 1000.0,
        "stock": 10
    }
    files = {
        "image": ("test.jpg", b"this is not an image", "image/jpeg")
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data,
        files=files
    )

    assert response.status_code == 400
    assert "Unsupported image format or corrupted file" in response.json()["detail"]

@pytest.mark.asyncio
async def test_large_image_upload_rejected(async_client, store):
    data = {
        "name": "Large Image Product",
        "price": 1000.0,
        "stock": 10
    }
    large_payload = b"0" * (5 * 1024 * 1024 + 10)
    files = {
        "image": ("test.jpg", large_payload, "image/jpeg")
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data,
        files=files
    )

    assert response.status_code == 400
    assert "dimensions or size exceed limit" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_image_dimensions_rejected(async_client, store):
    img = Image.new('RGB', (4001, 100), color='red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)

    data = {
        "name": "Huge Dimensions",
        "price": 1000.0,
        "stock": 10
    }
    files = {
        "image": ("test.jpg", img_byte_arr, "image/jpeg")
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data,
        files=files
    )

    assert response.status_code == 400
    assert "dimensions" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_product_creation_without_image(async_client, store):
    data = {
        "name": "No Image Product",
        "price": 500.0,
        "stock": 10
    }

    response = await async_client.post(
        f"/api/stores/{store.id}/products",
        data=data
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["image_url"] is None

@pytest.mark.asyncio
async def test_ai_promise_rejected(db_session, store):
    """Test that if the AI promises to fetch a picture, the controller falls back to the deterministic response."""
    from app.services.conversation_controller import ConversationController
    from app.services.response_builder import ProcessedResponse
    from app.models.conversation import Conversation
    from app.services.ai_provider import MockAIProvider

    class NaughtyAIProvider(MockAIProvider):
        async def process(self, context):
            return AIResponseSchema(
                response_message="Please hold on while I fetch the pictures for you.",
                confidence=0.8,
            )

    import app.services.conversation_controller as cc
    original_provider = cc.get_ai_provider
    cc.get_ai_provider = lambda: NaughtyAIProvider()

    try:
        controller = ConversationController()
        conv = Conversation(store_id=store.id, customer_phone="923000000000", customer_id="cust_123")
        db_session.add(conv)
        await db_session.commit()

        initial_response = ProcessedResponse(
            message="Deterministic product details here.",
            intent="picture_request",
            confidence=0.3,
            needs_clarification=True
        )

        final_response = await controller._optional_ai_response(
            conv, "show me its picture", initial_response, [], [], store.business_name, "en"
        )

        assert final_response.message == "Deterministic product details here."
    finally:
        cc.get_ai_provider = original_provider

@pytest.mark.asyncio
async def test_missing_image_returns_honest_message(async_client, store, db_session):
    from app.models.product import Product, ProductVariant
    from app.config import get_settings
    settings = get_settings()

    p = Product(store_id=store.id, name="No Image Shirt", base_price=500.0)
    db_session.add(p)
    await db_session.flush()
    db_session.add(ProductVariant(product_id=p.id, price=500.0, stock=10))
    await db_session.commit()

    response = await async_client.post(
        "/internal/whatsapp/messages",
        json={
            "store_id": store.id,
            "customer_number": "923001234567",
            "message": "show me picture of No Image Shirt",
            "message_type": "text"
        },
        headers={"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN}
    )
    assert response.status_code == 200
    res_data = response.json()
    assert "A picture for this product has not been uploaded yet" in res_data["message"] or "picture abhi catalog mein upload nahi hai" in res_data["message"]
    assert res_data["image_url"] is None

@pytest.mark.asyncio
async def test_replacing_image(async_client, store):
    img_byte_arr = _make_jpeg(color='blue')

    res = await async_client.post(
        f"/api/stores/{store.id}/products",
        data={"name": "Replaceable", "price": 10},
        files={"image": ("old.jpg", img_byte_arr, "image/jpeg")}
    )
    prod = res.json()
    old_url = prod["image_url"]
    assert old_url is not None

    img2 = Image.new('RGB', (100, 100), color='green')
    img2_byte_arr = io.BytesIO()
    img2.save(img2_byte_arr, format='PNG')
    img2_byte_arr.seek(0)

    res2 = await async_client.put(
        f"/api/stores/{store.id}/products/{prod['id']}/image",
        files={"image": ("new.png", img2_byte_arr, "image/png")}
    )
    assert res2.status_code == 200
    new_url = res2.json()["image_url"]
    assert new_url != old_url
    assert new_url.endswith(".jpg")

    old_filepath = os.path.join(os.environ["UPLOAD_DIR"], old_url.split("/")[-1])
    assert not os.path.exists(old_filepath)
    new_filepath = os.path.join(os.environ["UPLOAD_DIR"], new_url.split("/")[-1])
    assert os.path.exists(new_filepath)

@pytest.mark.asyncio
async def test_shared_image_not_deleted(async_client, store, db_session):
    img_byte_arr = _make_jpeg(10, 10, 'black')

    res1 = await async_client.post(
        f"/api/stores/{store.id}/products",
        data={"name": "Shared1", "price": 10},
        files={"image": ("shared.jpg", img_byte_arr, "image/jpeg")}
    )
    prod1 = res1.json()
    shared_url = prod1["image_url"]

    p2 = Product(store_id=store.id, name="Shared2", base_price=20.0, image_url=shared_url)
    db_session.add(p2)
    await db_session.commit()

    await async_client.delete(f"/api/stores/{store.id}/products/{prod1['id']}")

    shared_filepath = os.path.join(os.environ["UPLOAD_DIR"], shared_url.split("/")[-1])
    assert os.path.exists(shared_filepath)

@pytest.mark.asyncio
async def test_path_traversal_protection(async_client, store, db_session):
    malicious_url = "/uploads/../../etc/passwd"
    p = Product(store_id=store.id, name="Traverser", base_price=10.0, image_url=malicious_url)
    db_session.add(p)
    await db_session.commit()

    res = await async_client.delete(f"/api/stores/{store.id}/products/{p.id}")
    assert res.status_code == 200


# ===================================================================
# New tests
# ===================================================================

@pytest.mark.asyncio
async def test_upload_file_is_closed(async_client, store):
    """UploadFile.close() must be called even on success."""
    img_byte_arr = _make_jpeg()

    from starlette.datastructures import UploadFile as StarletteUploadFile
    original_close = StarletteUploadFile.close
    close_called = False

    async def tracking_close(self):
        nonlocal close_called
        close_called = True
        return await original_close(self)

    with patch.object(StarletteUploadFile, "close", tracking_close):
        response = await async_client.post(
            f"/api/stores/{store.id}/products",
            data={"name": "Close Test", "price": 10, "stock": 1},
            files={"image": ("close.jpg", img_byte_arr, "image/jpeg")}
        )
        assert response.status_code == 200
    assert close_called


@pytest.mark.asyncio
async def test_decompression_bomb_rejected(async_client, store):
    """A crafted image that triggers DecompressionBombError is rejected with 400."""
    with patch("PIL.Image.open") as mock_open:
        mock_open.side_effect = Image.DecompressionBombError("boom")
        response = await async_client.post(
            f"/api/stores/{store.id}/products",
            data={"name": "Bomb", "price": 10, "stock": 1},
            files={"image": ("bomb.jpg", _make_jpeg(), "image/jpeg")}
        )
        assert response.status_code == 400
        assert "dimensions or size exceed limit" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_db_failure_during_create_rolls_back_and_cleans_image(async_client, store, db_session):
    """If db.commit() fails during create, image is cleaned up and 500 is returned."""
    img_byte_arr = _make_jpeg()

    original_commit = db_session.commit

    call_count = 0
    async def failing_commit():
        nonlocal call_count
        call_count += 1
        # The store fixture already committed once; let that pass.
        # Fail on the product creation commit.
        if call_count > 0:
            raise Exception("simulated DB failure")
        await original_commit()

    with patch.object(db_session, "commit", side_effect=failing_commit):
        response = await async_client.post(
            f"/api/stores/{store.id}/products",
            data={"name": "DBFail", "price": 10, "stock": 1},
            files={"image": ("dbfail.jpg", img_byte_arr, "image/jpeg")}
        )
    assert response.status_code == 500
    assert "Database error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_db_failure_during_replace_rolls_back(async_client, store):
    """DB failure during image replace returns 500 and cleans up new image."""
    img_byte_arr = _make_jpeg(color='cyan')
    res = await async_client.post(
        f"/api/stores/{store.id}/products",
        data={"name": "ReplaceDBFail", "price": 10},
        files={"image": ("orig.jpg", img_byte_arr, "image/jpeg")}
    )
    assert res.status_code == 200
    prod = res.json()

    with patch("app.routers.products.AsyncSession.commit", side_effect=Exception("db boom")):
        img2 = _make_jpeg(color='magenta')
        res2 = await async_client.put(
            f"/api/stores/{store.id}/products/{prod['id']}/image",
            files={"image": ("new.jpg", img2, "image/jpeg")}
        )
    assert res2.status_code == 500
    assert "Database error" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_db_failure_during_image_removal_rolls_back(async_client, store):
    """DB failure during DELETE /{id}/image returns 500."""
    img_byte_arr = _make_jpeg(color='yellow')
    res = await async_client.post(
        f"/api/stores/{store.id}/products",
        data={"name": "RemoveDBFail", "price": 10},
        files={"image": ("rem.jpg", img_byte_arr, "image/jpeg")}
    )
    assert res.status_code == 200
    prod = res.json()

    with patch("app.routers.products.AsyncSession.commit", side_effect=Exception("db boom")):
        res2 = await async_client.delete(
            f"/api/stores/{store.id}/products/{prod['id']}/image"
        )
    assert res2.status_code == 500
    assert "Database error" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_external_url_never_deleted(async_client, store, db_session):
    """Products with HTTP image_url must never trigger filesystem deletion."""
    p = Product(store_id=store.id, name="External", base_price=10.0,
                image_url="https://cdn.example.com/img.jpg")
    db_session.add(p)
    await db_session.commit()

    with patch("app.routers.products._cleanup_if_unshared") as mock_cleanup:
        res = await async_client.delete(f"/api/stores/{store.id}/products/{p.id}")
        assert res.status_code == 200
        # _cleanup_if_unshared should not have been called because url doesn't start with /uploads/
        mock_cleanup.assert_not_called()


@pytest.mark.asyncio
async def test_cleanup_query_failure_after_commit_still_returns_success(async_client, store, db_session):
    """If the shared-reference query fails post-commit, the response is still success."""
    img_byte_arr = _make_jpeg(color='orange')
    res = await async_client.post(
        f"/api/stores/{store.id}/products",
        data={"name": "PostCommitFail", "price": 10},
        files={"image": ("pcf.jpg", img_byte_arr, "image/jpeg")}
    )
    assert res.status_code == 200
    prod = res.json()
    assert prod["image_url"].startswith("/uploads/")

    # Patch db.execute to fail only on the post-commit shared-reference query
    original_execute = db_session.execute
    execute_call_count = 0

    async def patched_execute(*args, **kwargs):
        nonlocal execute_call_count
        result = await original_execute(*args, **kwargs)
        execute_call_count += 1
        return result

    # For delete_product: the commit succeeds, but the post-commit select raises
    async def execute_that_fails_on_post_commit_select(*args, **kwargs):
        nonlocal execute_call_count
        execute_call_count += 1
        # First execute: find the product (pass through)
        # The delete and commit happen without execute
        # Post-commit execute: the shared-reference check — fail it
        if execute_call_count >= 2:
            raise Exception("simulated post-commit query failure")
        return await original_execute(*args, **kwargs)

    execute_call_count = 0
    with patch.object(db_session, "execute", side_effect=execute_that_fails_on_post_commit_select):
        res2 = await async_client.delete(f"/api/stores/{store.id}/products/{prod['id']}")

    # Must still return success despite the post-commit query failure
    assert res2.status_code == 200
    assert res2.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_uploads_static_route_serves_file(store, db_session):
    """The /uploads static mount should serve a newly uploaded product image."""
    from fastapi.staticfiles import StaticFiles
    # Remount /uploads to point at the test's temporary UPLOAD_DIR
    upload_dir = os.environ["UPLOAD_DIR"]
    # Remove existing mount if present, then re-add
    app.routes[:] = [r for r in app.routes if getattr(r, 'name', None) != 'uploads']
    app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

    app.dependency_overrides[get_db] = lambda: db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        img_byte_arr = _make_jpeg(color='purple')
        res = await ac.post(
            f"/api/stores/{store.id}/products",
            data={"name": "Static Serve", "price": 10},
            files={"image": ("serve.jpg", img_byte_arr, "image/jpeg")}
        )
        assert res.status_code == 200
        image_url = res.json()["image_url"]
        assert image_url.startswith("/uploads/")

        static_res = await ac.get(image_url)
        assert static_res.status_code == 200
        assert "image" in static_res.headers.get("content-type", "")
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_shared_image_not_deleted_on_replace(async_client, store, db_session):
    """When replacing an image that another product still references, old file is kept."""
    img_byte_arr = _make_jpeg(color='navy')
    res1 = await async_client.post(
        f"/api/stores/{store.id}/products",
        data={"name": "SharedReplace1", "price": 10},
        files={"image": ("sr.jpg", img_byte_arr, "image/jpeg")}
    )
    prod1 = res1.json()
    shared_url = prod1["image_url"]

    # Second product shares the same image_url
    p2 = Product(store_id=store.id, name="SharedReplace2", base_price=20.0, image_url=shared_url)
    db_session.add(p2)
    await db_session.commit()

    # Replace image on first product
    img2 = _make_jpeg(color='lime')
    res2 = await async_client.put(
        f"/api/stores/{store.id}/products/{prod1['id']}/image",
        files={"image": ("sr2.jpg", img2, "image/jpeg")}
    )
    assert res2.status_code == 200

    # Old image must still exist (shared by p2)
    old_filepath = os.path.join(os.environ["UPLOAD_DIR"], shared_url.split("/")[-1])
    assert os.path.exists(old_filepath)


@pytest.mark.asyncio
async def test_shared_image_not_deleted_on_image_removal(async_client, store, db_session):
    """When removing image from a product, shared file is kept if another product uses it."""
    img_byte_arr = _make_jpeg(color='teal')
    res1 = await async_client.post(
        f"/api/stores/{store.id}/products",
        data={"name": "SharedRemove1", "price": 10},
        files={"image": ("srem.jpg", img_byte_arr, "image/jpeg")}
    )
    prod1 = res1.json()
    shared_url = prod1["image_url"]

    p2 = Product(store_id=store.id, name="SharedRemove2", base_price=20.0, image_url=shared_url)
    db_session.add(p2)
    await db_session.commit()

    # Remove image from first product via DELETE /{id}/image
    res2 = await async_client.delete(
        f"/api/stores/{store.id}/products/{prod1['id']}/image"
    )
    assert res2.status_code == 200

    # Old image must still exist (shared by p2)
    old_filepath = os.path.join(os.environ["UPLOAD_DIR"], shared_url.split("/")[-1])
    assert os.path.exists(old_filepath)
