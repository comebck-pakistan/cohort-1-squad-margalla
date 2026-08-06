"""Product management routes."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pathlib import Path
import os
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import structlog

from app.database import get_db
from app.models.product import Product, ProductAlias, ProductVariant
from app.models.store import Store
from app.schemas.api import ProductResponse

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Upload-directory helpers (shared with main.py via get_upload_dir)
# ---------------------------------------------------------------------------

def get_upload_dir() -> Path:
    """Return the resolved upload directory as a pathlib.Path."""
    env = os.environ.get("UPLOAD_DIR")
    if env:
        return Path(env).resolve()
    return (Path(__file__).resolve().parent.parent.parent / "uploads").resolve()


def get_safe_filepath(filename: str) -> Path | None:
    """Return a resolved path inside UPLOAD_DIR, or None if unsafe."""
    if not filename:
        return None
    safe_name = Path(filename).name          # strip directory components
    if not safe_name or safe_name != filename:
        return None
    upload_dir = get_upload_dir()
    filepath = (upload_dir / safe_name).resolve()
    # Ensure resolved path is truly inside UPLOAD_DIR
    try:
        filepath.relative_to(upload_dir)
    except ValueError:
        return None
    return filepath


def _cleanup_local_image(image_url: str) -> None:
    """Best-effort delete of a local /uploads/ file.  Never raises."""
    if not image_url or not image_url.startswith("/uploads/"):
        return
    # Never touch external URLs
    if image_url.startswith("http://") or image_url.startswith("https://"):
        return
    filename = image_url.split("/")[-1]
    filepath = get_safe_filepath(filename)
    if filepath and filepath.exists():
        try:
            filepath.unlink()
        except Exception:
            logger.error("image_cleanup_failed", error="Could not delete file")


def _cleanup_if_unshared(image_url: str, db_result_scalars) -> None:
    """Delete local file only when no other product references it."""
    if not image_url or not image_url.startswith("/uploads/"):
        return
    if image_url.startswith("http://") or image_url.startswith("https://"):
        return
    filename = image_url.split("/")[-1]
    filepath = get_safe_filepath(filename)
    if not filepath:
        return
    if not db_result_scalars and filepath.exists():
        try:
            filepath.unlink()
        except Exception:
            logger.error("image_cleanup_failed", error="Could not delete file")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(
    prefix="/api/stores/{store_id}/products",
    tags=["products"]
)


@router.get("", response_model=list[ProductResponse])
async def list_products(store_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .where(Product.store_id == store_id)
        .options(selectinload(Product.variants))
    )
    return result.scalars().all()


async def _process_image_upload(image: UploadFile) -> str:
    import io
    from PIL import Image as PILImage, UnidentifiedImageError, ImageOps
    try:
        import pillow_heif
        try:
            pillow_heif.register_heif_opener()
            pillow_heif.register_avif_opener()
        except AttributeError:
            pass
    except ImportError:
        pass

    try:
        content = await image.read()
        if len(content) > 5 * 1024 * 1024:
            raise ValueError("Image size exceeds 5MB limit.")

        # Prevent decompression bomb
        PILImage.MAX_IMAGE_PIXELS = 16_000_000

        with PILImage.open(io.BytesIO(content)) as img:
            # Force full decode so bombs/corrupt data fail here
            img.load()

            if img.width > 4000 or img.height > 4000:
                raise ValueError("Image dimensions exceed 4000x4000 limit.")

            img = ImageOps.exif_transpose(img)

            # Convert to RGB (JPEG doesn't support alpha channel)
            if img.mode in ('RGBA', 'P', 'LA') or getattr(img, 'format', '') in ('AVIF', 'HEIF', 'WEBP', 'PNG'):
                img = img.convert('RGB')

            # Resize if too large
            img.thumbnail((2048, 2048), PILImage.Resampling.LANCZOS)

            upload_dir = get_upload_dir()
            upload_dir.mkdir(parents=True, exist_ok=True)

            filename = f"{uuid.uuid4().hex}.jpg"
            filepath = get_safe_filepath(filename)
            if not filepath:
                raise ValueError("Invalid generated filename.")
            img.save(str(filepath), "JPEG", quality=85, optimize=True)

        return f"/uploads/{filename}"
    except PILImage.DecompressionBombError:
        raise HTTPException(status_code=400, detail="Image dimensions or size exceed limit.")
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="Unsupported image format or corrupted file.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Image dimensions or size exceed limit.")
    except HTTPException:
        raise
    except Exception:
        logger.error("image_processing_failed", error="Image processing failed")
        raise HTTPException(status_code=400, detail="Image processing failed.")
    finally:
        await image.close()


@router.post("", response_model=ProductResponse)
async def create_product(
    store_id: str,
    name: str = Form(...),
    price: float = Form(...),
    stock: int = Form(1),
    category: str = Form(None),
    description: str = Form(None),
    labels: str = Form(None),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db)
):
    # Verify store exists
    store = await db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    image_url = None
    if image:
        image_url = await _process_image_upload(image)

    try:
        new_product = Product(
            store_id=store_id,
            name=name,
            category=category,
            description=description,
            base_price=price,
            image_url=image_url
        )
        db.add(new_product)
        await db.flush()

        variant = ProductVariant(
            product_id=new_product.id,
            price=price,
            stock=stock,
        )
        db.add(variant)

        if labels:
            label_list = [label.strip() for label in labels.split(",") if label.strip()]
            for label in label_list:
                alias = ProductAlias(
                    product_id=new_product.id,
                    alias=label
                )
                db.add(alias)

        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("product_creation_failed", error="Database error during product creation")
        _cleanup_local_image(image_url)
        raise HTTPException(status_code=500, detail="Database error occurred")

    # Reload with relationships
    await db.refresh(new_product, ["variants", "aliases"])
    return new_product

@router.delete("/{product_id}")
async def delete_product(store_id: str, product_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Store image_url for deletion before deleting product
    image_url_to_delete = product.image_url

    await db.delete(product)
    await db.commit()

    # Post-commit cleanup: failures here are logged, never HTTP 500
    if image_url_to_delete and image_url_to_delete.startswith("/uploads/"):
        try:
            res = await db.execute(select(Product).where(Product.image_url == image_url_to_delete))
            shared = res.scalars().all()
            _cleanup_if_unshared(image_url_to_delete, shared)
        except Exception:
            logger.error("post_commit_cleanup_failed", error="Shared-reference query failed after delete")

    return {"status": "deleted"}

from pydantic import BaseModel
class UpdateStockRequest(BaseModel):
    stock: int

@router.patch("/{product_id}/stock")
async def update_stock(store_id: str, product_id: str, request: UpdateStockRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id).options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if not product.variants:
        raise HTTPException(status_code=400, detail="Product has no variants")

    # Just update the first variant for simplicity in MVP
    product.variants[0].stock = request.stock
    await db.commit()
    return {"status": "updated", "stock": request.stock}

@router.put("/{product_id}/image")
async def replace_product_image(
    store_id: str,
    product_id: str,
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    new_image_url = await _process_image_upload(image)
    old_image_url = product.image_url

    try:
        product.image_url = new_image_url
        await db.commit()
    except Exception:
        await db.rollback()
        # Clean up new image if db fails
        _cleanup_local_image(new_image_url)
        raise HTTPException(status_code=500, detail="Database error occurred")

    # Post-commit cleanup of old image: failures logged, never HTTP 500
    if old_image_url and old_image_url.startswith("/uploads/"):
        try:
            res = await db.execute(select(Product).where(Product.image_url == old_image_url))
            shared = res.scalars().all()
            _cleanup_if_unshared(old_image_url, shared)
        except Exception:
            logger.error("post_commit_cleanup_failed", error="Shared-reference query failed after replace")

    return {"status": "updated", "image_url": new_image_url}

@router.delete("/{product_id}/image")
async def delete_product_image(
    store_id: str,
    product_id: str,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if not product.image_url:
        return {"status": "deleted"}

    old_image_url = product.image_url

    try:
        product.image_url = None
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database error occurred")

    # Post-commit cleanup: failures logged, never HTTP 500
    if old_image_url and old_image_url.startswith("/uploads/"):
        try:
            res = await db.execute(select(Product).where(Product.image_url == old_image_url))
            shared = res.scalars().all()
            _cleanup_if_unshared(old_image_url, shared)
        except Exception:
            logger.error("post_commit_cleanup_failed", error="Shared-reference query failed after image removal")

    return {"status": "deleted"}
