"""Category model — seller-managed catalog categories.

Each category belongs to exactly one store. Category names are unique within a
store (the same name may exist in different stores). Inactive/empty categories
stay fully manageable by the seller but are never shown to customers.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index("ix_categories_store_id", "store_id"),
        # Name unique within a store; same name allowed across stores.
        UniqueConstraint("store_id", "name", name="uq_categories_store_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # One-directional relationship (no back_populates) to avoid touching Store.
    store: Mapped["Store"] = relationship("Store")


from app.models.store import Store
