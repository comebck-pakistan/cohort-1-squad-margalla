"""WhatsApp connection and conversation management routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database import get_db
from app.models.store import Store
from app.models.whatsapp import WhatsAppSession
from app.models.conversation import Conversation
from app.models.handoff import HumanHandoff
from app.models.order import Order
from app.schemas.api import (
    WhatsAppStatusResponse, WhatsAppQRResponse, ConversationResponse, OrderResponse,
)
from app.config import get_settings
import httpx
import asyncio

router = APIRouter(prefix="/api/stores/{store_id}", tags=["whatsapp", "conversations", "orders"])


def _get_gateway_url() -> str:
    """Get the gateway URL from settings."""
    return get_settings().GATEWAY_URL


# --- WhatsApp routes ---

@router.post("/whatsapp/connect")
async def connect_whatsapp(store_id: str, db: AsyncSession = Depends(get_db)):
    """Initiate WhatsApp connection for a store."""
    store = await _get_store(store_id, db)

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

    store.whatsapp_status = "initializing"
    await db.commit()

    # Call gateway asynchronously so we don't block
    async def _call_gateway():
        settings = get_settings()
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    f"{_get_gateway_url()}/sessions/{store_id}/connect",
                    headers={"X-Internal-Token": settings.INTERNAL_SERVICE_TOKEN},
                    timeout=30.0
                )
            except Exception as e:
                print(f"Gateway connect error: {e}")

    asyncio.create_task(_call_gateway())

    return {"status": "initializing", "store_id": store_id}


@router.get("/whatsapp/status", response_model=WhatsAppStatusResponse)
async def whatsapp_status(store_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    result = await db.execute(
        select(WhatsAppSession).where(WhatsAppSession.store_id == store_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return {"store_id": store_id, "status": "disconnected"}
    
    # Try fetching QR code from gateway if we are waiting
    qr_code = None
    if session.status in ("initializing", "waiting_for_qr"):
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(f"{_get_gateway_url()}/sessions/{store_id}/qr", timeout=2.0)
                if res.status_code == 200:
                    qr_code = res.json().get("qr_code")
            except Exception:
                pass

    return {
        "store_id": store_id,
        "status": session.status,
        "phone_number": session.phone_number,
        "qr_code": qr_code
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
    result = await db.execute(
        select(Order).where(Order.store_id == store_id)
    )
    orders = result.scalars().all()
    return [
        OrderResponse(
            id=o.id, store_id=o.store_id, status=o.status,
            total_amount=o.total_amount, customer_name=o.customer_name,
            customer_phone=o.customer_phone, payment_method=o.payment_method,
            created_at=str(o.created_at),
        ) for o in orders
    ]


# --- Helpers ---

async def _get_store(store_id: str, db: AsyncSession) -> Store:
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store
