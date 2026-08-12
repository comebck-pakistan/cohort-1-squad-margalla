"""Category management routes — seller-managed, store-scoped catalog categories.

Every query is filtered by store_id: a category (and its image) can only ever be
read or mutated through its owning store. Image handling reuses the safe upload
utilities from the products router (validation, path-traversal protection,
share-aware cleanup).
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
import structlog

from app.database import get_db
from app.models.store import Store
from app.models.category import Category
from app.models.product import Product
from app.schemas.api import CategoryCreate, CategoryUpdate, CategoryResponse
from app.routers.products import (
    _process_image_upload, get_safe_filepath, MAX_CATEGORY_LEN,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/stores/{store_id}/categories", tags=["categories"])


async def _get_store(store_id: str, db: AsyncSession) -> Store:
    store = await db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


async def _get_category(store_id: str, category_id: str, db: AsyncSession) -> Category:
    """Load a category scoped to its store, or 404. Enforces store isolation."""
    result = await db.execute(
        select(Category).where(Category.id == category_id, Category.store_id == store_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


async def _product_count(store_id: str, category_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(Product.id)).where(
            Product.store_id == store_id, Product.category_id == category_id
        )
    )
    return int(result.scalar() or 0)


def _to_response(category: Category, product_count: int) -> CategoryResponse:
    return CategoryResponse(
        id=category.id, store_id=category.store_id, name=category.name,
        description=category.description, image_url=category.image_url,
        display_order=category.display_order, is_active=category.is_active,
        product_count=product_count,
    )


async def _cleanup_category_image_if_unshared(image_url: str, db: AsyncSession) -> None:
    """Delete a local /uploads file only when no product OR category references it."""
    if not image_url or not image_url.startswith("/uploads/"):
        return
    if image_url.startswith("http://") or image_url.startswith("https://"):
        return
    prod_refs = (await db.execute(
        select(Product.id).where(Product.image_url == image_url).limit(1)
    )).first()
    cat_refs = (await db.execute(
        select(Category.id).where(Category.image_url == image_url).limit(1)
    )).first()
    if prod_refs or cat_refs:
        return  # still referenced — never delete
    filepath = get_safe_filepath(image_url.split("/")[-1])
    if filepath and filepath.exists():
        try:
            filepath.unlink()
        except Exception:
            logger.error("category_image_cleanup_failed", error="Could not delete file")


@router.get("", response_model=list[CategoryResponse])
async def list_categories(store_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    result = await db.execute(
        select(Category)
        .where(Category.store_id == store_id)
        .order_by(Category.display_order, Category.name)
    )
    categories = result.scalars().all()
    # Product counts per category in one grouped query.
    counts_result = await db.execute(
        select(Product.category_id, func.count(Product.id))
        .where(Product.store_id == store_id, Product.category_id.isnot(None))
        .group_by(Product.category_id)
    )
    counts = {cid: n for cid, n in counts_result.all()}
    return [_to_response(c, counts.get(c.id, 0)) for c in categories]


@router.post("", response_model=CategoryResponse)
async def create_category(
    store_id: str, data: CategoryCreate, db: AsyncSession = Depends(get_db)
):
    await _get_store(store_id, db)
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name cannot be empty")
    if len(name) > MAX_CATEGORY_LEN:
        raise HTTPException(status_code=400, detail=f"Category name too long (max {MAX_CATEGORY_LEN})")

    category = Category(
        store_id=store_id, name=name,
        description=(data.description or None),
        display_order=data.display_order, is_active=data.is_active,
    )
    db.add(category)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A category with this name already exists in this store")
    await db.refresh(category)
    return _to_response(category, 0)


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(store_id: str, category_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    category = await _get_category(store_id, category_id, db)
    return _to_response(category, await _product_count(store_id, category_id, db))


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    store_id: str, category_id: str, data: CategoryUpdate, db: AsyncSession = Depends(get_db)
):
    await _get_store(store_id, db)
    category = await _get_category(store_id, category_id, db)

    if data.name is not None:
        name = data.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Category name cannot be empty")
        if len(name) > MAX_CATEGORY_LEN:
            raise HTTPException(status_code=400, detail=f"Category name too long (max {MAX_CATEGORY_LEN})")
        category.name = name
    if data.description is not None:
        category.description = data.description or None
    if data.display_order is not None:
        category.display_order = data.display_order
    if data.is_active is not None:
        category.is_active = data.is_active

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A category with this name already exists in this store")
    await db.refresh(category)
    return _to_response(category, await _product_count(store_id, category_id, db))


@router.delete("/{category_id}")
async def delete_category(store_id: str, category_id: str, db: AsyncSession = Depends(get_db)):
    await _get_store(store_id, db)
    category = await _get_category(store_id, category_id, db)

    count = await _product_count(store_id, category_id, db)
    if count > 0:
        # Never silently delete products. Seller must move/remove them first.
        raise HTTPException(
            status_code=409,
            detail=f"Category is not empty ({count} product(s)). Move or remove them first.",
        )

    old_image = category.image_url
    await db.delete(category)
    await db.commit()
    if old_image:
        try:
            await _cleanup_category_image_if_unshared(old_image, db)
        except Exception:
            logger.error("post_commit_cleanup_failed", error="category image cleanup after delete")
    return {"status": "deleted"}


@router.post("/{category_id}/image", response_model=CategoryResponse)
async def upload_category_image(
    store_id: str, category_id: str,
    image: UploadFile = File(...), db: AsyncSession = Depends(get_db),
):
    await _get_store(store_id, db)
    category = await _get_category(store_id, category_id, db)

    new_url = await _process_image_upload(image)  # validates type/size/dimensions
    old_url = category.image_url
    try:
        category.image_url = new_url
        await db.commit()
    except Exception:
        await db.rollback()
        # roll back the just-written file
        await _cleanup_category_image_if_unshared(new_url, db)
        raise HTTPException(status_code=500, detail="Database error occurred")
    await db.refresh(category)
    if old_url and old_url != new_url:
        try:
            await _cleanup_category_image_if_unshared(old_url, db)
        except Exception:
            logger.error("post_commit_cleanup_failed", error="category image cleanup after replace")
    return _to_response(category, await _product_count(store_id, category_id, db))


@router.delete("/{category_id}/image", response_model=CategoryResponse)
async def delete_category_image(
    store_id: str, category_id: str, db: AsyncSession = Depends(get_db)
):
    await _get_store(store_id, db)
    category = await _get_category(store_id, category_id, db)
    old_url = category.image_url
    if not old_url:
        return _to_response(category, await _product_count(store_id, category_id, db))
    try:
        category.image_url = None
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred")
    try:
        await _cleanup_category_image_if_unshared(old_url, db)
    except Exception:
        logger.error("post_commit_cleanup_failed", error="category image cleanup after removal")
    return _to_response(category, await _product_count(store_id, category_id, db))
