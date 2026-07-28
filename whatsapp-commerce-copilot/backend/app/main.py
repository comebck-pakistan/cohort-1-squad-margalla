"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.database import init_db, create_tables
from app.routers import health, demo, stores, products, internal, whatsapp


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB on startup."""
    settings = get_settings()
    engine, _ = init_db(settings.DATABASE_URL)
    await create_tables(engine)
    yield
    await engine.dispose()


app = FastAPI(
    title="WhatsApp Commerce Copilot",
    description="Multi-store WhatsApp AI sales assistant",
    version="0.1.0",
    lifespan=lifespan,
)

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
from app.routers.demo import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
app.include_router(health.router)
app.include_router(demo.router)
app.include_router(stores.router)
app.include_router(products.router)
app.include_router(internal.router)
app.include_router(whatsapp.router)
