"""Order and OrderItem models."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_store_id", "store_id"),
        Index("ix_orders_conversation_id", "conversation_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("conversations.id"), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(64), ForeignKey("customers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending, confirmed, processing, shipped, delivered, cancelled
    total_amount: Mapped[float] = mapped_column(Float, default=0.0)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer_city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", lazy="selectin", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    variant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    variant_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="items")


from app.models.store import Store
