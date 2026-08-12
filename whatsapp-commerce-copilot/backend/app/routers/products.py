"""Product management routes."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pathlib import Path
import json
import os
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
import structlog

from app.database import get_db
from app.models.product import Product, ProductAlias, ProductVariant
from app.models.category import Category
from app.models.store import Store
from app.schemas.api import ProductResponse, MoveProductRequest

logger = structlog.get_logger()

# --- Validation limits ---
MAX_NAME_LEN = 255
MAX_SKU_LEN = 100
MAX_CATEGORY_LEN = 100
MAX_DESCRIPTION_LEN = 5000


def _parse_variants(raw: str | None, default_price: float) -> list[dict]:
    """Parse and validate the optional variants JSON payload.

    Raises HTTPException(400) with a precise, safe message on any problem.
    Returns a list of normalized variant dicts (empty when none supplied).
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid variants payload: not valid JSON")
    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="Invalid variants payload: expected a list")

    normalized: list[dict] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="Invalid variants payload: each variant must be an object")
        price = entry.get("price", default_price)
        stock = entry.get("stock", 0)
        try:
            price = float(price)
            stock = int(stock)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Variant price/stock must be numeric")
        if price < 0:
            raise HTTPException(status_code=400, detail="Price cannot be negative")
        if stock < 0:
            raise HTTPException(status_code=400, detail="Stock cannot be negative")
        v_sku = (entry.get("sku") or "").strip() or None
        if v_sku and len(v_sku) > MAX_SKU_LEN:
            raise HTTPException(status_code=400, detail=f"SKU too long (max {MAX_SKU_LEN} characters)")
        color = (entry.get("color") or "").strip() or None
        size = (entry.get("size") or "").strip() or None
        normalized.append({
            "color": color,
            "size": size,
            "price": price,
            "stock": stock,
            "sku": v_sku,
            "is_active": bool(entry.get("is_active", True)),
        })
    return normalized


async def _validate_category(db: AsyncSession, store_id: str, category_id: str | None) -> None:
    """Ensure a category_id (if given) exists and belongs to this store.

    Cross-store assignment is rejected with 400 so a product can never be filed
    under another store's category.
    """
    if not category_id:
        return
    result = await db.execute(
        select(Category.id).where(Category.id == category_id, Category.store_id == store_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=400, detail="Category not found in this store")


async def _assert_unique_store_skus(db: AsyncSession, store_id: str, new_skus: list[str]) -> None:
    """Enforce store-scoped SKU uniqueness across product and variant SKUs.

    Comparison is case-insensitive so it matches catalog-search SKU lookups.
    Raises HTTPException(400) on any duplicate (within the request or in the DB).
    """
    upper = [s.upper() for s in new_skus if s]
    if not upper:
        return
    if len(upper) != len(set(upper)):
        raise HTTPException(status_code=400, detail="Duplicate store-level SKU in request")

    existing_products = await db.execute(
        select(Product.sku).where(Product.store_id == store_id, Product.sku.isnot(None))
    )
    existing = {s.upper() for (s,) in existing_products.all() if s}
    existing_variants = await db.execute(
        select(ProductVariant.sku)
        .join(Product, ProductVariant.product_id == Product.id)
        .where(Product.store_id == store_id, ProductVariant.sku.isnot(None))
    )
    existing |= {s.upper() for (s,) in existing_variants.all() if s}

    for s in upper:
        if s in existing:
            raise HTTPException(status_code=400, detail="Duplicate store-level SKU")

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
async def list_products(
    store_id: str,
    category_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List a store's products, optionally filtered by category.

    category_id="uncategorized" (or "none") returns products with no category.
    """
    query = select(Product).where(Product.store_id == store_id).options(selectinload(Product.variants))
    if category_id in ("uncategorized", "none"):
        query = query.where(Product.category_id.is_(None))
    elif category_id:
        query = query.where(Product.category_id == category_id)
    result = await db.execute(query)
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
    category_id: str = Form(None),
    description: str = Form(None),
    sku: str = Form(None),
    labels: str = Form(None),
    is_active: bool = Form(True),
    variants: str = Form(None),
    image: UploadFile = File(None),
    db: AsyncSession = Depends(get_db)
):
    # Verify store exists
    store = await db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    # --- Validate cheap scalar fields BEFORE touching the image or DB ---
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if len(name) > MAX_NAME_LEN:
        raise HTTPException(status_code=400, detail=f"Name too long (max {MAX_NAME_LEN} characters)")
    if price is None or price < 0:
        raise HTTPException(status_code=400, detail="Price cannot be negative")
    if stock is None or stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    category = (category or "").strip() or None
    if category and len(category) > MAX_CATEGORY_LEN:
        raise HTTPException(status_code=400, detail=f"Category too long (max {MAX_CATEGORY_LEN} characters)")
    category_id = (category_id or "").strip() or None
    await _validate_category(db, store_id, category_id)
    if description and len(description) > MAX_DESCRIPTION_LEN:
        raise HTTPException(status_code=400, detail=f"Description too long (max {MAX_DESCRIPTION_LEN} characters)")
    sku = (sku or "").strip() or None
    if sku and len(sku) > MAX_SKU_LEN:
        raise HTTPException(status_code=400, detail=f"SKU too long (max {MAX_SKU_LEN} characters)")

    parsed_variants = _parse_variants(variants, default_price=price)

    # Store-level SKU uniqueness across product + variant SKUs (case-insensitive)
    await _assert_unique_store_skus(
        db, store_id, [sku] + [v["sku"] for v in parsed_variants]
    )

    # --- Process image only after validation passes (avoids orphaned uploads) ---
    image_url = None
    if image:
        image_url = await _process_image_upload(image)

    try:
        new_product = Product(
            store_id=store_id,
            name=name,
            category=category,
            category_id=category_id,
            description=description,
            base_price=price,
            sku=sku,
            is_active=is_active,
            image_url=image_url,
        )
        db.add(new_product)
        await db.flush()

        if parsed_variants:
            for v in parsed_variants:
                db.add(ProductVariant(product_id=new_product.id, **v))
        else:
            # Legacy single-variant behavior: derive one default variant.
            db.add(ProductVariant(
                product_id=new_product.id,
                price=price,
                stock=stock,
                is_active=True,
            ))

        if labels:
            label_list = [label.strip() for label in labels.split(",") if label.strip()]
            for label in label_list:
                db.add(ProductAlias(product_id=new_product.id, alias=label))

        await db.commit()
    except IntegrityError:
        # DB-level unique constraint (store_id, sku) — race with a concurrent insert.
        await db.rollback()
        _cleanup_local_image(image_url)
        raise HTTPException(status_code=400, detail="Duplicate store-level SKU")
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


class ActiveRequest(BaseModel):
    is_active: bool


@router.patch("/{product_id}/stock")
async def update_stock(store_id: str, product_id: str, request: UpdateStockRequest, db: AsyncSession = Depends(get_db)):
    if request.stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id).options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if not product.variants:
        raise HTTPException(status_code=400, detail="Product has no variants")

    # Legacy MVP endpoint: updates the first variant. New callers should use the
    # variant-specific endpoint below so the correct variant is updated.
    product.variants[0].stock = request.stock
    await db.commit()
    return {"status": "updated", "stock": request.stock}


@router.patch("/{product_id}/variants/{variant_id}/stock")
async def update_variant_stock(
    store_id: str,
    product_id: str,
    variant_id: str,
    request: UpdateStockRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update the stock of a specific variant (never silently the first one)."""
    if request.stock < 0:
        raise HTTPException(status_code=400, detail="Stock cannot be negative")
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id, Product.store_id == store_id)
        .options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    variant = next((v for v in product.variants if v.id == variant_id), None)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    variant.stock = request.stock
    await db.commit()
    return {"status": "updated", "stock": variant.stock, "variant_id": variant_id}


@router.patch("/{product_id}/active")
async def set_product_active(
    store_id: str,
    product_id: str,
    request: ActiveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Toggle a product's active status (store-scoped)."""
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = request.is_active
    await db.commit()
    return {"status": "updated", "is_active": product.is_active}


@router.patch("/{product_id}/category")
async def move_product_category(
    store_id: str,
    product_id: str,
    request: MoveProductRequest,
    db: AsyncSession = Depends(get_db),
):
    """Move a product to another category (or to Uncategorized when null).

    The target category must belong to the same store.
    """
    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.store_id == store_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    target = (request.category_id or "").strip() or None
    await _validate_category(db, store_id, target)
    product.category_id = target
    await db.commit()
    return {"status": "updated", "category_id": target}


@router.patch("/{product_id}/variants/{variant_id}/active")
async def set_variant_active(
    store_id: str,
    product_id: str,
    variant_id: str,
    request: ActiveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Toggle a specific variant's active status (store-scoped)."""
    result = await db.execute(
        select(Product)
        .where(Product.id == product_id, Product.store_id == store_id)
        .options(selectinload(Product.variants))
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    variant = next((v for v in product.variants if v.id == variant_id), None)
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    variant.is_active = request.is_active
    await db.commit()
    return {"status": "updated", "is_active": variant.is_active}

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
