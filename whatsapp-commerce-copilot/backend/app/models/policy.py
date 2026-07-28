"""Store policy model."""
import uuid
from sqlalchemy import String, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class StorePolicy(Base):
    __tablename__ = "store_policies"
    __table_args__ = (
        Index("ix_store_policies_store_id", "store_id"),
        Index("ix_store_policies_type", "store_id", "policy_type"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    policy_type: Mapped[str] = mapped_column(String(50), nullable=False)  # cod, delivery, returns, exchange, delivery_locations, delivery_charges
    policy_value: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="policies")


from app.models.store import Store
