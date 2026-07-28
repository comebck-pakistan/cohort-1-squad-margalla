"""WhatsApp session model."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class WhatsAppSession(Base):
    __tablename__ = "whatsapp_sessions"
    __table_args__ = (
        Index("ix_whatsapp_sessions_store_id", "store_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="disconnected")
    # Status values: disconnected, initializing, waiting_for_qr, authenticated, connected, reconnecting, failed
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    session_data_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qr_code: Mapped[str | None] = mapped_column(String(2000), nullable=True)  # Base64 encoded QR
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="whatsapp_sessions")


from app.models.store import Store
