"""Server-side seller session model.

The browser only ever holds an opaque random token in an HttpOnly cookie; the
database stores only a SHA-256 hash of that token, so a DB leak cannot be
replayed as a live session. Sessions are revocable (logout / expiry).
"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index("ix_auth_sessions_token_hash", "token_hash", unique=True),
        Index("ix_auth_sessions_store_id", "store_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    # SHA-256 hex digest of the opaque cookie token (never the token itself).
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # The store this session is authorized for (one seller ↔ one store).
    store_id: Mapped[str] = mapped_column(String(64), ForeignKey("stores.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
