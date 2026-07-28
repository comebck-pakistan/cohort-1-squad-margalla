"""Store model."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_language: Mapped[str] = mapped_column(String(20), default="roman_urdu")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    whatsapp_status: Mapped[str] = mapped_column(String(30), default="disconnected")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    products: Mapped[list["Product"]] = relationship("Product", back_populates="store", lazy="selectin")
    policies: Mapped[list["StorePolicy"]] = relationship("StorePolicy", back_populates="store", lazy="selectin")
    conversations: Mapped[list["Conversation"]] = relationship("Conversation", back_populates="store", lazy="selectin")
    whatsapp_sessions: Mapped[list["WhatsAppSession"]] = relationship("WhatsAppSession", back_populates="store", lazy="selectin")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="store", lazy="selectin")
    customers: Mapped[list["Customer"]] = relationship("Customer", back_populates="store", lazy="selectin")


# Forward reference imports at module level for type hints
from app.models.product import Product
from app.models.policy import StorePolicy
from app.models.conversation import Conversation
from app.models.whatsapp import WhatsAppSession
from app.models.order import Order
from app.models.customer import Customer
