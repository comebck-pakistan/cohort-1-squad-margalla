"""Application configuration via environment variables."""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./dev.db"

    # Backend
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    DEBUG: bool = True

    # Internal service auth
    INTERNAL_SERVICE_TOKEN: str = "dev-internal-token"

    # Seller authentication (single shared admin password → store-bound session)
    # AUTH_ENABLED defaults False so local dev/demo stays anonymous and the
    # existing dashboard keeps working. Production MUST set AUTH_ENABLED=true and
    # a strong SELLER_ADMIN_PASSWORD.
    AUTH_ENABLED: bool = False
    SELLER_ADMIN_PASSWORD: Optional[str] = None
    SESSION_TTL_SECONDS: int = 86400  # 24h
    SESSION_COOKIE_NAME: str = "wcc_session"
    COOKIE_SECURE: bool = False  # set True in production (HTTPS only)
    COOKIE_SAMESITE: str = "lax"

    # AI Provider
    AI_PROVIDER: str = "gemini"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    GEMINI_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # WhatsApp Gateway
    GATEWAY_PORT: int = 3001
    BACKEND_URL: str = "http://localhost:8000"
    GATEWAY_URL: str = "http://localhost:3001"

    # Public base used to turn a stored relative image path ("/uploads/x.jpg")
    # into an absolute URL that WhatsApp's media fetcher can actually reach.
    # Falls back to BACKEND_URL, which is correct inside Docker (the Evolution
    # container resolves "backend" on the compose network). MUST be set to a
    # publicly reachable host in production — a localhost value is unreachable
    # from anywhere but the machine itself.
    PUBLIC_MEDIA_BASE_URL: Optional[str] = None

    @property
    def media_base_url(self) -> str:
        return (self.PUBLIC_MEDIA_BASE_URL or self.BACKEND_URL or "").rstrip("/")

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # Rate Limiting
    RATE_LIMIT_DEMO: str = "10/minute"
    RATE_LIMIT_INTERNAL: str = "100/minute"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings():
    """Reset settings singleton (for testing)."""
    global _settings
    _settings = None
