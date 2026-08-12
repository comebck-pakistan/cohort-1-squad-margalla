"""Conversation and Message models."""
import uuid
import json
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, Index, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_store_id", "store_id"),
        Index("ix_conversations_customer_id", "customer_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(64), ForeignKey("customers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active")  # active, closed, escalated

    # Conversation context
    current_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_variant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    selected_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    order_stage: Mapped[str] = mapped_column(String(50), default="BROWSING")
    pending_clarification: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string of clarification data
    clarification_candidates: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string of candidate product IDs
    
    # State tracking
    preferences: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string of collected entities (category, style, color, etc.)
    recently_shown_products: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string of list of product IDs

    # Category-browse state. menu_snapshot is the exact numbered menu last shown
    # so numbered replies ("2", "second one") resolve against what the customer
    # actually saw. browse_category_id + browse_offset drive product pagination.
    category_menu_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {"kind","items":[{"n","id","name"}], ...}
    browse_category_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browse_offset: Mapped[int] = mapped_column(Integer, default=0)

    # Language preference ("en" or "ur")
    preferred_response_language: Mapped[str] = mapped_column(String(10), default="en")
    last_detected_input_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language_confidence: Mapped[float] = mapped_column(default=0.0)

    # Control
    is_ai_controlled: Mapped[bool] = mapped_column(Boolean, default=True)
    conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Customer details for order
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="conversations")
    customer: Mapped["Customer"] = relationship("Customer", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation", lazy="selectin", order_by="Message.created_at")
    handoffs: Mapped[list["HumanHandoff"]] = relationship("HumanHandoff", back_populates="conversation", lazy="selectin")

    def get_clarification_candidates_list(self) -> list[str]:
        """Get clarification candidate IDs as a list."""
        if not self.clarification_candidates:
            return []
        try:
            return json.loads(self.clarification_candidates)
        except (json.JSONDecodeError, TypeError):
            return []

    def set_clarification_candidates_list(self, candidates: list[str]):
        """Set clarification candidate IDs from a list."""
        self.clarification_candidates = json.dumps(candidates)

    def get_preferences(self) -> dict:
        """Get collected preferences as a dictionary."""
        if not self.preferences:
            return {}
        try:
            return json.loads(self.preferences)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_preferences(self, prefs: dict):
        """Set preferences dictionary."""
        self.preferences = json.dumps(prefs)

    def get_recently_shown_products(self) -> list[str]:
        """Get recently shown product IDs."""
        if not self.recently_shown_products:
            return []
        try:
            return json.loads(self.recently_shown_products)
        except (json.JSONDecodeError, TypeError):
            return []

    def add_recently_shown_products(self, product_ids: list[str]):
        """Add product IDs to the recently shown list, keeping the 5 most recent."""
        recent = self.get_recently_shown_products()
        for pid in product_ids:
            if pid in recent:
                recent.remove(pid)
            recent.append(pid)
        # Keep only the last 5
        self.recently_shown_products = json.dumps(recent[-5:])

    # --- Category-menu snapshot helpers ---

    def get_menu_snapshot(self) -> dict | None:
        """Return the last shown numbered menu, or None."""
        if not self.category_menu_snapshot:
            return None
        try:
            return json.loads(self.category_menu_snapshot)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_menu_snapshot(self, snapshot: dict | None):
        """Persist (or clear) the numbered menu snapshot."""
        self.category_menu_snapshot = json.dumps(snapshot) if snapshot else None

    def clear_browse_state(self):
        """Clear category-browse pagination + snapshot."""
        self.category_menu_snapshot = None
        self.browse_category_id = None
        self.browse_offset = 0

    # --- Language helpers ---

    def get_preferred_response_language(self) -> str:
        """Return 'en' or 'ur'. Defaults to 'en'."""
        return self.preferred_response_language or "en"

    def set_language_preference(
        self,
        input_language: str,
        response_language: str,
        confidence: float,
    ):
        """Update session language preference.

        Only updates when the message is clearly language-bearing
        (not a neutral reply). Callers must gate on is_neutral themselves.
        """
        self.last_detected_input_language = input_language
        self.preferred_response_language = response_language
        self.language_confidence = confidence


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        UniqueConstraint("whatsapp_message_id", name="uq_messages_whatsapp_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversations.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound, outbound
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text")  # text, image, audio, document
    whatsapp_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processed_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON of processing result
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")

    def get_processed_result(self) -> dict | None:
        if not self.processed_result_json:
            return None
        try:
            return json.loads(self.processed_result_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def set_processed_result(self, result: dict):
        self.processed_result_json = json.dumps(result)


from app.models.store import Store
from app.models.customer import Customer
from app.models.handoff import HumanHandoff
