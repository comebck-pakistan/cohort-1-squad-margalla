"""Product, ProductAlias, and ProductVariant models."""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, Float, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_store_id", "store_id"),
        Index("ix_products_sku", "store_id", "sku", unique=True),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    store: Mapped["Store"] = relationship("Store", back_populates="products")
    aliases: Mapped[list["ProductAlias"]] = relationship("ProductAlias", back_populates="product", lazy="selectin", cascade="all, delete-orphan")
    variants: Mapped[list["ProductVariant"]] = relationship("ProductVariant", back_populates="product", lazy="selectin", cascade="all, delete-orphan")


class ProductAlias(Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        Index("ix_product_aliases_alias", "alias"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("products.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="aliases")


class ProductVariant(Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        Index("ix_product_variants_product_id", "product_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("products.id"), nullable=False)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="variants")


from app.models.store import Store
