"""Store management routes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.store import Store
from app.schemas.api import StoreCreate, StoreResponse

router = APIRouter(prefix="/api/stores", tags=["stores"])


@router.post("", response_model=StoreResponse, status_code=201)
async def create_store(data: StoreCreate, db: AsyncSession = Depends(get_db)):
    store = Store(
        id=data.id or None,
        business_name=data.business_name,
        owner_name=data.owner_name,
        owner_phone=data.owner_phone,
        owner_email=data.owner_email,
        preferred_language=data.preferred_language,
        ai_enabled=data.ai_enabled,
    )
    db.add(store)
    await db.flush()
    return store


@router.get("", response_model=list[StoreResponse])
async def list_stores(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store))
    return result.scalars().all()


@router.get("/{store_id}", response_model=StoreResponse)
async def get_store(store_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Store).where(Store.id == store_id))
    store = result.scalar_one_or_none()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store
