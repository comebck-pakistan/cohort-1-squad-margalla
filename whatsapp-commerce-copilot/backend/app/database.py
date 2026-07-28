"""Database connection and session management."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


def get_engine(database_url: str | None = None):
    """Create async engine. Accepts override URL for testing."""
    url = database_url or get_settings().DATABASE_URL
    connect_args = {}
    if "sqlite" in url:
        connect_args["check_same_thread"] = False
    return create_async_engine(url, echo=False, connect_args=connect_args)


def get_session_factory(engine=None):
    """Create session factory."""
    if engine is None:
        engine = get_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Default engine and session factory (lazy init)
_engine = None
_session_factory = None


def init_db(database_url: str | None = None):
    """Initialize database engine and session factory."""
    global _engine, _session_factory
    _engine = get_engine(database_url)
    _session_factory = get_session_factory(_engine)
    return _engine, _session_factory


def get_db_engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


def get_db_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory()
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes to get a DB session."""
    factory = get_db_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables(engine=None):
    """Create all tables (for dev/testing). Use Alembic in production."""
    if engine is None:
        engine = get_db_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables(engine=None):
    """Drop all tables (for testing only)."""
    if engine is None:
        engine = get_db_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
