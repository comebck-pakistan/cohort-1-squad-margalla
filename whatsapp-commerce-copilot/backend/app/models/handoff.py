"""Human handoff model."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class HumanHandoff(Base):
    __tablename__ = "human_handoffs"
    __table_args__ = (
        Index("ix_human_handoffs_store_id", "store_id"),
        Index("ix_human_handoffs_conversation_id", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversations.id"), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    # Reasons: low_confidence, missing_product, complaint, negotiation, wholesale, refund, explicit_request, repeated_failure, ai_error
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending, active, resolved
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="handoffs")


from app.models.conversation import Conversation
