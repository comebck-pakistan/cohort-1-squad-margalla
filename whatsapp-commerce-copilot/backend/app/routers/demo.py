"""Demo message simulator endpoint.

POST /api/demo/messages — runs the full message processing pipeline
without requiring a WhatsApp connection.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.database import get_db
from app.models.store import Store
from app.models.product import Product
from app.models.policy import StorePolicy
from app.schemas.api import DemoMessageRequest, DemoMessageResponse
from app.services.conversation_controller import ConversationController
from app.services.conversation_manager import ConversationManager, DuplicateMessageError

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(tags=["demo"])

# Singleton processor
_controller = ConversationController()
_conv_manager = ConversationManager()


@router.post("/api/demo/messages", response_model=DemoMessageResponse)
@limiter.limit("10/minute")
async def demo_message(
    request: Request,
    data: DemoMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Process a demo message through the full pipeline.

    This endpoint runs the same processing pipeline as real WhatsApp messages
    but without requiring a WhatsApp connection.
    """
    # Validate non-empty message
    if not data.message or not data.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    # Load store
    result = await db.execute(select(Store).where(Store.id == data.store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store '{data.store_id}' not found")

    # Load store's products (with variants and aliases)
    products_result = await db.execute(
        select(Product)
        .where(Product.store_id == data.store_id, Product.is_active == True)
        .options(
            selectinload(Product.variants),
            selectinload(Product.aliases),
        )
    )
    products = list(products_result.scalars().all())

    # Load store's policies
    policies_result = await db.execute(
        select(StorePolicy).where(StorePolicy.store_id == data.store_id)
    )
    policies = list(policies_result.scalars().all())

    # Get or create conversation
    conv, customer = await _conv_manager.get_or_create_conversation(db, store.id, data.customer_number)

    # Save inbound message
    try:
        inbound = await _conv_manager.save_message(
            db, conv, data.message, "inbound",
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
        # AI is disabled, return empty/silent response
        await db.commit()
        return DemoMessageResponse(
            message="[AI disabled - human mode active]",
            intent="human_control",
            confidence=1.0,
            matched_product_id=None,
            store_id=store.id,
        )

    # Process message
    response = await _controller.process(
        db=db,
        conversation=conv,
        message=data.message,
        products=products,
        policies=policies,
        store_name=store.business_name,
        store_language=store.preferred_language,
        store_id=store.id,
        customer_number=data.customer_number,
    )

    inbound.set_processed_result(response.to_dict())
    await _conv_manager.save_message(db, conv, response.message, "outbound")
    await db.commit()

    return DemoMessageResponse(**response.to_dict())
