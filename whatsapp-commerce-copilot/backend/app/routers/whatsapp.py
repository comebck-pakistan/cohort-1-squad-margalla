"""WhatsApp connection and conversation management routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.database import get_db
from app.models.store import Store
from app.models.whatsapp import WhatsAppSession
from app.models.conversation import Conversation
from app.models.handoff import HumanHandoff
from app.models.order import Order
from app.schemas.api import (
    WhatsAppStatusResponse, WhatsAppQRResponse, ConversationResponse, OrderResponse, ConnectWhatsAppRequest,
)
from app.config import get_settings
from app.utils.phone import normalize_phone_number, PHONE_HELP_MESSAGE
import httpx
import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/stores/{store_id}", tags=["whatsapp", "conversations", "orders"])

# Stale session threshold: sessions stuck in initializing beyond this are failed.
STALE_SESSION_SECONDS = 120


def _get_gateway_url() -> str:
    """Get the gateway URL from settings."""
    return get_settings().GATEWAY_URL


# --- WhatsApp routes ---

@router.post("/whatsapp/connect")
async def connect_whatsapp(store_id: str, req: ConnectWhatsAppRequest = None, db: AsyncSession = Depends(get_db)):
    """Initiate WhatsApp connection for a store."""
    store = await _get_store(store_id, db)

    # Validate/normalize phone BEFORE mutating any state or calling the gateway.
    # Empty/None -> QR path (no phone). Present-but-invalid -> 422, no side effects.
    try:
        normalized_phone = normalize_phone_number(req.phone_number if req else None)
    except ValueError:
        raise HTTPException(status_code=422, detail=PHONE_HELP_MESSAGE)

    # Get or create session
    result = await db.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == store_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        session = WhatsAppSession(store_id=store_id, status="initializing")
        db.add(session)
    else:
        session.status = "initializing"
        session.qr_code = None  # Clear stale QR

    store.whatsapp_status = "initializing"
    await db.commit()

    # Call gateway synchronously with bounded timeout
    settings = get_settings()
    try:
        async with httpx.AsyncClient() as client:
            json_body = {}
            if normalized_phone:
                json_body["phoneNumber"] = normalized_phone

            resp = await client.post(
                f"{_get_gateway_url()}/sessions/{store_id}/connect",
                json=json_body,
                headers={"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN},
                timeout=15.0
            )
            resp.raise_for_status()
            gw_data = resp.json()

            # Persist QR if returned immediately by gateway
            qr_code = gw_data.get("qr_code")
            pairing_code = gw_data.get("pairing_code")
            if gw_data.get("status") == "connected":
                # Instance was already open — the gateway declined to destroy it.
                session.status = "connected"
                session.qr_code = None
                session.pairing_code = None
                store.whatsapp_status = "connected"
            elif qr_code or pairing_code:
                if qr_code:
                    session.qr_code = qr_code
                if pairing_code:
                    session.pairing_code = pairing_code
                session.status = "waiting_for_qr"
                store.whatsapp_status = "waiting_for_qr"
            # else: QR will arrive later via webhook

            await db.commit()
            return {
                "status": session.status,
                "store_id": store_id,
                "qr_code": qr_code,
                "pairing_code": pairing_code,
            }

    except httpx.TimeoutException:
        logger.error("gateway_connect_timeout", store_id=store_id)
        session.status = "failed"
        store.whatsapp_status = "failed"
        await db.commit()
        raise HTTPException(status_code=504, detail="WhatsApp service timed out. Please try again.")

    except httpx.HTTPStatusError as e:
        # Map upstream gateway status to a safe client status. Never surface the
        # internal gateway URL, MDN link, or raw upstream body to the dashboard.
        upstream = e.response.status_code
        logger.error("gateway_connect_http_error", store_id=store_id, upstream_status=upstream)
        session.status = "failed"
        store.whatsapp_status = "failed"
        await db.commit()
        if upstream in (400, 422):
            raise HTTPException(status_code=422, detail=PHONE_HELP_MESSAGE)
        if upstream == 409:
            raise HTTPException(status_code=409, detail="This WhatsApp session is already being set up. Please wait a moment and try again.")
        if upstream == 504:
            raise HTTPException(status_code=504, detail="WhatsApp service timed out. Please try again.")
        raise HTTPException(status_code=502, detail="WhatsApp service is currently unavailable. Please try again.")

    except Exception as e:
        logger.error("gateway_connect_error", store_id=store_id, error=str(e))
        session.status = "failed"
        store.whatsapp_status = "failed"
        await db.commit()
        raise HTTPException(status_code=502, detail="WhatsApp service is currently unavailable. Please try again.")


@router.get("/whatsapp/status", response_model=WhatsAppStatusResponse)
async def whatsapp_status(store_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    result = await db.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == store_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return {"store_id": store_id, "status": "disconnected"}

    # Stale session recovery: if stuck in initializing for too long, mark failed
    if session.status == "initializing" and session.updated_at:
        age = datetime.utcnow() - session.updated_at
        if age > timedelta(seconds=STALE_SESSION_SECONDS):
            logger.warning("stale_session_recovered", store_id=store_id, age_seconds=age.total_seconds())
            session.status = "failed"
            # Update store too
            store_result = await db.execute(select(Store).where(Store.id == store_id))
            store = store_result.scalar_one_or_none()
            if store:
                store.whatsapp_status = "failed"
            await db.commit()

    # Use DB QR as primary source
    qr_code = session.qr_code

    # Fallback: try gateway cache only if DB has no QR and we're still waiting
    if not qr_code and session.status in ("initializing", "waiting_for_qr"):
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{_get_gateway_url()}/sessions/{store_id}/qr",
                    timeout=2.0,
                )
                if res.status_code == 200:
                    gw_qr = res.json().get("qr_code")
                    if gw_qr:
                        qr_code = gw_qr
                        # Persist gateway QR to DB for durability
                        session.qr_code = gw_qr
                        session.status = "waiting_for_qr"
                        await db.commit()
        except Exception:
            pass

    return {
        "store_id": store_id,
        "status": session.status,
        "phone_number": session.phone_number,
        "qr_code": qr_code,
        "pairing_code": session.pairing_code,
    }


@router.get("/whatsapp/qr", response_model=WhatsAppQRResponse)
async def whatsapp_qr(store_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    result = await db.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == store_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return WhatsAppQRResponse(store_id=store_id, qr_code=None, status="disconnected")
    return WhatsAppQRResponse(
        store_id=store_id,
        qr_code=session.qr_code,
        status=session.status,
    )


@router.delete("/whatsapp")
async def disconnect_whatsapp(store_id: str, db: AsyncSession = Depends(get_db)):
    store = await _get_store(store_id, db)
    result = await db.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == store_id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.status = "disconnected"
        session.qr_code = None  # Clear stale QR
        session.pairing_code = None # Clear stale pairing code
    store.whatsapp_status = "disconnected"
    await db.commit()

    # Call gateway to disconnect
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        try:
            await client.delete(
                f"{_get_gateway_url()}/sessions/{store_id}",
                headers={"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN},
                timeout=5.0
            )
        except Exception:
            pass

    return {"status": "disconnected", "store_id": store_id}


# --- Conversation routes ---

@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(store_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    result = await db.execute(
        select(Conversation).where(Conversation.store_id == store_id).options(selectinload(Conversation.customer))
    )
    convs = result.scalars().all()
    return [
        ConversationResponse(
            id=c.id, store_id=c.store_id, customer_id=c.customer_id,
            customer_phone=c.customer.phone_number if c.customer else None,
            status=c.status, is_ai_controlled=c.is_ai_controlled,
            order_stage=c.order_stage, created_at=str(c.created_at),
        ) for c in convs
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(store_id: str, conversation_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.store_id == store_id,
        ).options(selectinload(Conversation.customer))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": conv.id,
        "store_id": conv.store_id,
        "customer_id": conv.customer_id,
        "customer_phone": conv.customer.phone_number if conv.customer else None,
        "status": conv.status,
        "is_ai_controlled": conv.is_ai_controlled,
        "order_stage": conv.order_stage,
        "messages": [
            {"id": m.id, "direction": m.direction, "content": m.content, "created_at": str(m.created_at)}
            for m in (conv.messages or [])
        ],
    }

class SendMessageRequest(BaseModel):
    message: str

@router.post("/conversations/{conversation_id}/send")
async def send_manual_message(store_id: str, conversation_id: str, request: SendMessageRequest, db: AsyncSession = Depends(get_db)):
    """Send a manual message from the human agent."""
    await _get_store(store_id, db)
    
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.store_id == store_id,
        ).options(selectinload(Conversation.customer))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    settings = get_settings()
    if not conv.customer:
        raise HTTPException(status_code=400, detail="Customer missing from conversation")
    customer_number = conv.customer.phone_number
    
    # Save the outbound message to DB first
    from app.models import Message as DbMessage
    db_msg = DbMessage(
        conversation_id=conv.id,
        direction="outbound",
        content=request.message,
    )
    db.add(db_msg)
    await db.commit()

    # Call gateway /send endpoint
    import httpx
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{settings.GATEWAY_URL}/send",
                json={
                    "store_id": store_id,
                    "customer_number": customer_number,
                    "message": request.message
                },
                headers={"x-internal-token": settings.INTERNAL_SERVICE_TOKEN},
                timeout=10.0
            )
            resp.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gateway failed: {str(e)}")

    return {"status": "sent"}

@router.post("/conversations/{conversation_id}/takeover")
async def takeover_conversation(store_id: str, conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Human takes over conversation — AI sends zero automatic replies."""
    await _get_store(store_id, db)
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.store_id == store_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.is_ai_controlled = False

    # Create handoff record
    handoff = HumanHandoff(
        conversation_id=conv.id,
        store_id=store_id,
        reason="manual_takeover",
        summary=f"Manual takeover requested for conversation {conv.id}",
        status="active",
    )
    db.add(handoff)

    return {"status": "human_control", "conversation_id": conv.id}


@router.post("/conversations/{conversation_id}/enable-ai")
async def enable_ai(store_id: str, conversation_id: str, db: AsyncSession = Depends(get_db)):
    """Return conversation to AI control."""
    await _get_store(store_id, db)
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.store_id == store_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conv.is_ai_controlled = True
    return {"status": "ai_control", "conversation_id": conv.id}


# --- Order routes ---

@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(store_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    # Eager-load line items so the seller can see exactly which products were
    # ordered. selectinload is required under async (lazy access would raise).
    result = await db.execute(
        select(Order)
        .where(Order.store_id == store_id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()
    return [
        OrderResponse(
            id=o.id, store_id=o.store_id, status=o.status,
            total_amount=o.total_amount, customer_name=o.customer_name,
            customer_phone=o.customer_phone,
            customer_address=o.customer_address, customer_city=o.customer_city,
            payment_method=o.payment_method,
            created_at=str(o.created_at),
            items=[
                OrderItemResponse(
                    product_id=it.product_id, variant_id=it.variant_id,
                    product_name=it.product_name,
                    variant_description=it.variant_description,
                    quantity=it.quantity, unit_price=it.unit_price,
                    line_total=it.unit_price * it.quantity,
                ) for it in o.items
            ],
        ) for o in orders
    ]


# --- Helpers ---

async def _get_store(store_id: str, db: AsyncSession) -> Store:
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store
