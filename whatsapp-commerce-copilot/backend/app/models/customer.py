"""Customer model."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_store_phone", "store_id", "phone_number", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="customers")
    conversations: Mapped[list["Conversation"]] = relationship("Conversation", back_populates="customer", lazy="selectin")


from app.models.store import Store
from app.models.conversation import Conversation
