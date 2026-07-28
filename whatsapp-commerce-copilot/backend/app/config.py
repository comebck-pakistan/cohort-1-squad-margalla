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

    # AI Provider
    AI_PROVIDER: str = "mock"
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

    # WhatsApp Gateway
    GATEWAY_PORT: int = 3001
    BACKEND_URL: str = "http://localhost:8000"
    GATEWAY_URL: str = "http://localhost:3001"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

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
