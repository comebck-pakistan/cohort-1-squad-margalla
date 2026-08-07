"""Seller authentication: single shared admin password → store-bound session.

Design (per stabilization decisions):
- One shared admin password (``SELLER_ADMIN_PASSWORD``) authenticates a login.
- Login mints an opaque random token; the DB stores only its SHA-256 hash.
- The token is returned as a Secure, HttpOnly, SameSite cookie (never readable
  by browser JS, never exposed to the SPA bundle).
- A session is bound to exactly one store_id (one seller ↔ one store); accessing
  another store's routes is rejected with 403.
- Enforcement is gated by ``AUTH_ENABLED``. When False (local/demo), the guards
  are no-ops so the existing anonymous flow and dashboard keep working. Production
  MUST set ``AUTH_ENABLED=true`` and a strong ``SELLER_ADMIN_PASSWORD``.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.auth import AuthSession


def _hash_token(token: str) -> str:
    """Return the SHA-256 hex digest stored in the DB for a cookie token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_admin_password(provided: str) -> bool:
    """Constant-time comparison against the configured admin password."""
    expected = get_settings().SELLER_ADMIN_PASSWORD
    if not expected:
        return False
    return secrets.compare_digest(provided or "", expected)


async def create_session(db: AsyncSession, store_id: str) -> str:
    """Create a server-side session for a store and return the opaque token."""
    settings = get_settings()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(seconds=settings.SESSION_TTL_SECONDS)
    db.add(AuthSession(token_hash=_hash_token(token), store_id=store_id, expires_at=expires_at))
    await db.flush()
    return token


async def _load_valid_session(request: Request, db: AsyncSession) -> AuthSession | None:
    """Return the live session for the request cookie, or None. Read-only."""
    settings = get_settings()
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return None
    result = await db.execute(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(token))
    )
    session = result.scalar_one_or_none()
    if session is None:
        return None
    if session.expires_at <= datetime.utcnow():
        return None  # expired sessions are inert
    return session


async def delete_session(request: Request, db: AsyncSession) -> None:
    """Revoke the session identified by the request cookie (logout)."""
    token = request.cookies.get(get_settings().SESSION_COOKIE_NAME)
    if not token:
        return
    result = await db.execute(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(token))
    )
    session = result.scalar_one_or_none()
    if session is not None:
        await db.delete(session)


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_TTL_SECONDS,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=get_settings().SESSION_COOKIE_NAME, path="/")


# --- FastAPI guard dependencies ---

async def require_seller_auth(
    store_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Guard for store-scoped seller routes (``/api/stores/{store_id}/...``).

    No-op when AUTH_ENABLED is False. Otherwise requires a valid session cookie
    bound to this exact store_id (401 if missing/invalid, 403 if wrong store).
    """
    if not get_settings().AUTH_ENABLED:
        return
    session = await _load_valid_session(request, db)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if session.store_id != store_id:
        raise HTTPException(status_code=403, detail="Not authorized for this store")


async def require_authenticated(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthSession | None:
    """Guard for routes without a store_id in the path (any valid session)."""
    if not get_settings().AUTH_ENABLED:
        return None
    session = await _load_valid_session(request, db)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return session
