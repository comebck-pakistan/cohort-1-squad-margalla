"""Internal routes for WhatsApp gateway communication.

Protected with X-Internal-Token header.
Handles: incoming messages, outbound send requests, session status events.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from slowapi import Limiter
from slowapi.util import get_remote_address

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
from app.services.message_processor import MessageProcessor
from app.services.conversation_manager import ConversationManager

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/internal/whatsapp", tags=["internal"])

_processor = MessageProcessor()
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

    # Save inbound message
    await _conv_manager.save_message(db, conv, data.message, "inbound")
    await db.commit()

    if not conv.is_ai_controlled:
        return DemoMessageResponse(
            message="[AI disabled - human mode active]",
            matched_product_id=None,
            store_id=store.id,
            customer_number=data.customer_number
        )

    # Process through pipeline
    response = _processor.process(
        message=data.message,
        products=products,
        policies=policies,
        store_name=store.business_name,
        store_language=store.preferred_language,
        store_id=store.id,
        customer_number=data.customer_number,
    )

    # Save outbound message
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

    # Also update store's whatsapp_status
    store_result = await db.execute(select(Store).where(Store.id == data.store_id))
    store = store_result.scalar_one_or_none()
    if store:
        store.whatsapp_status = data.status

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
