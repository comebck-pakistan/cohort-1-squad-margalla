"""Conversation and Message models."""
import uuid
import json
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, Index, JSON
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


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_whatsapp_id", "whatsapp_message_id"),
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


from app.models.store import Store
from app.models.customer import Customer
from app.models.handoff import HumanHandoff
