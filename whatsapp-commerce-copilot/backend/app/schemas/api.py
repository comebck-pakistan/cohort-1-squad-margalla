"""Pydantic schemas for API request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional


# --- Store schemas ---
class StoreCreate(BaseModel):
    id: Optional[str] = None
    business_name: str
    owner_name: str
    owner_phone: Optional[str] = None
    owner_email: Optional[str] = None
    preferred_language: str = "roman_urdu"
    ai_enabled: bool = True


class StoreResponse(BaseModel):
    id: str
    business_name: str
    owner_name: str
    preferred_language: str
    ai_enabled: bool
    whatsapp_status: str

    model_config = {"from_attributes": True}


# --- Product schemas ---
class VariantResponse(BaseModel):
    id: str
    color: Optional[str] = None
    size: Optional[str] = None
    price: float
    stock: int
    sku: Optional[str] = None

    model_config = {"from_attributes": True}


class ProductResponse(BaseModel):
    id: str
    store_id: str
    name: str
    category: Optional[str] = None
    sku: Optional[str] = None
    description: Optional[str] = None
    base_price: Optional[float] = None
    image_url: Optional[str] = None
    is_active: bool
    variants: list[VariantResponse] = []

    model_config = {"from_attributes": True}


# --- Demo message schemas ---
class DemoMessageRequest(BaseModel):
    store_id: str = Field(..., description="Store ID to process message for")
    customer_number: str = Field(..., min_length=1, description="Customer phone number")
    message: str = Field(..., min_length=1, max_length=4096, description="Customer message text")
    whatsapp_message_id: Optional[str] = Field(None, description="WhatsApp message ID for dedup")


class DemoMessageResponse(BaseModel):
    message: str
    intent: str
    confidence: float
    matched_product_id: Optional[str] = None
    matched_variant_id: Optional[str] = None
    image_url: Optional[str] = None
    sources: list[str] = []
    extracted_entities: dict = {}
    clarification_options: Optional[list[dict]] = None
    needs_clarification: bool = False
    needs_human: bool = False
    escalation_reason: Optional[str] = None
    store_id: str


# --- WhatsApp schemas ---
class WhatsAppStatusResponse(BaseModel):
    store_id: str
    status: str
    phone_number: Optional[str] = None
    qr_code: Optional[str] = None


class WhatsAppQRResponse(BaseModel):
    store_id: str
    qr_code: Optional[str] = None
    status: str


# --- Internal message schemas ---
class InternalMessageRequest(BaseModel):
    store_id: str
    customer_number: str
    message: str
    message_type: str = "text"
    whatsapp_message_id: Optional[str] = None


class InternalSendRequest(BaseModel):
    store_id: str
    customer_number: str
    message: str


class InternalSessionEvent(BaseModel):
    store_id: str
    status: str
    phone_number: Optional[str] = None
    error: Optional[str] = None
    qr_code: Optional[str] = None


# --- Conversation schemas ---
class ConversationResponse(BaseModel):
    id: str
    store_id: str
    customer_id: str
    customer_phone: Optional[str] = None
    status: str
    is_ai_controlled: bool
    order_stage: str
    created_at: str

    model_config = {"from_attributes": True}


# --- Order schemas ---
class OrderResponse(BaseModel):
    id: str
    store_id: str
    status: str
    total_amount: float
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    payment_method: Optional[str] = None
    created_at: str

    model_config = {"from_attributes": True}


# --- Health ---
class HealthResponse(BaseModel):
    status: str
    service: str = "whatsapp-commerce-copilot-backend"
    version: str = "0.1.0"
