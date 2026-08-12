"""Internal routes for WhatsApp gateway communication.

Protected with X-Internal-Token header.
Handles: incoming messages, outbound send requests, session status events.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from app.config import get_settings
from app.database import get_db
from app.models.store import Store
from app.models.product import Product
from app.models.policy import StorePolicy
from app.models.whatsapp import WhatsAppSession
from app.schemas.api import (
    InternalMessageRequest, InternalSendRequest, InternalSessionEvent,
    DemoMessageResponse,
)
from app.services.conversation_controller import ConversationController
from app.services.conversation_manager import ConversationManager, DuplicateMessageError

logger = structlog.get_logger()
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/internal/whatsapp", tags=["internal"])

_controller = ConversationController()
_conv_manager = ConversationManager()


def _verify_internal_token(x_internal_token: str = Header(None)):
    """Verify the internal service token."""
    settings = get_settings()
    if x_internal_token != settings.INTERNAL_SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid internal token")


@router.post("/messages")
@limiter.limit("100/minute")
async def receive_message(
    request: Request,
    data: InternalMessageRequest,
    db: AsyncSession = Depends(get_db),
    _token: None = Depends(_verify_internal_token),
):
    """Receive a message forwarded from the WhatsApp gateway."""
    # Load store
    result = await db.execute(select(Store).where(Store.id == data.store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    # Load products and policies
    products_result = await db.execute(
        select(Product)
        .where(Product.store_id == data.store_id, Product.is_active == True)
        .options(selectinload(Product.variants), selectinload(Product.aliases))
    )
    products = list(products_result.scalars().all())

    policies_result = await db.execute(
        select(StorePolicy).where(StorePolicy.store_id == data.store_id)
    )
    policies = list(policies_result.scalars().all())

    # Get or create conversation
    conv, customer = await _conv_manager.get_or_create_conversation(db, store.id, data.customer_number)

    # Persist the provider message ID before doing any work. Re-delivery returns
    # the already computed response and never sends a second order/reply.
    try:
        inbound = await _conv_manager.save_message(
            db, conv, data.message, "inbound",
            message_type=data.message_type,
            whatsapp_message_id=data.whatsapp_message_id,
        )
        await db.flush()
    except (DuplicateMessageError, IntegrityError) as exc:
        await db.rollback()
        existing = await _conv_manager.get_message_by_whatsapp_id(
            db, data.whatsapp_message_id
        )
        saved = existing.get_processed_result() if existing else None
        if saved:
            return DemoMessageResponse(**saved)
        return DemoMessageResponse(
            message="", intent="duplicate", confidence=1.0,
            store_id=store.id,
        )

    if not conv.is_ai_controlled:
        await db.commit()
        return DemoMessageResponse(
            message="[AI disabled - human mode active]",
            intent="human_control",
            confidence=1.0,
            matched_product_id=None,
            store_id=store.id,
        )

    # Capture scalar store fields before processing so an error path can build a
    # response without touching the ORM object after a rollback expires it.
    store_id = store.id
    store_name = store.business_name
    store_language = store.preferred_language

    # Assemble optional visual context for inbound image messages. Only build it
    # when the gateway actually forwarded vision output — text/audio are unaffected.
    vision = None
    if data.message_type == "image" and (
        data.vision_description or data.vision_attributes or data.vision_text_ocr
    ):
        vision = {
            "description": data.vision_description,
            "text_ocr": data.vision_text_ocr,
            "attributes": data.vision_attributes or [],
            "confidence": data.vision_confidence,
            "original_caption": data.original_caption,
        }

    # Process through pipeline. A processing/DB failure must return a truthful
    # temporary-service response — never fabricated product data — with a 200 so
    # the gateway can retry the un-persisted message later.
    try:
        response = await _controller.process(
            db=db,
            conversation=conv,
            message=data.message,
            products=products,
            policies=policies,
            store_name=store_name,
            store_language=store_language,
            store_id=store_id,
            customer_number=data.customer_number,
            vision=vision,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("message_processing_failed", store_id=store_id)
        await db.rollback()
        from app.services.i18n import t
        lang = "ur" if store_language in ("ur", "roman_urdu") else "en"
        return DemoMessageResponse(
            message=t("service_unavailable", lang),
            intent="error",
            confidence=0.0,
            matched_product_id=None,
            store_id=store_id,
        )

    inbound.set_processed_result(response.to_dict())
    await _conv_manager.save_message(db, conv, response.message, "outbound")
    await db.commit()

    return DemoMessageResponse(**response.to_dict())


@router.post("/session-events")
async def session_event(
    data: InternalSessionEvent,
    db: AsyncSession = Depends(get_db),
    _token: None = Depends(_verify_internal_token),
):
    """Receive session status events from the gateway."""
    # Update or create WhatsApp session record
    result = await db.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == data.store_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        session = WhatsAppSession(store_id=data.store_id)
        db.add(session)

    session.status = data.status
    if data.phone_number:
        session.phone_number = data.phone_number

    # Persist QR code when provided by gateway webhook
    if data.qr_code:
        session.qr_code = data.qr_code

    # Persist or clear pairing code from gateway lifecycle events
    if data.pairing_code is not None:
        session.pairing_code = data.pairing_code

    # Clear QR and pairing code on terminal states (connected, disconnected, failed)
    if data.status in ("connected", "disconnected", "failed"):
        session.qr_code = None
        session.pairing_code = None

    # Record connection timestamp
    if data.status == "connected":
        from datetime import datetime
        session.last_connected_at = datetime.utcnow()

    # Also update store's whatsapp_status
    store_result = await db.execute(select(Store).where(Store.id == data.store_id))
    store = store_result.scalar_one_or_none()
    if store:
        store.whatsapp_status = data.status

    await db.commit()
    return {"status": "ok"}


@router.post("/send")
async def send_message(
    data: InternalSendRequest,
    _token: None = Depends(_verify_internal_token),
):
    """Request to send a message through the gateway.

    Note: In production, this would forward to the gateway service.
    For MVP, this is a placeholder that the gateway polls or the
    backend calls the gateway's /send endpoint directly.
    """
    # In a full implementation, this would call the gateway's HTTP endpoint
    # For now, return acknowledgment
    return {"status": "queued", "store_id": data.store_id}
