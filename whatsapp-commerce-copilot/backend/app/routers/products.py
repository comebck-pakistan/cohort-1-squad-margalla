"""Product management routes."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import os
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.product import Product, ProductAlias, ProductVariant
from app.models.store import Store
from app.schemas.api import ProductResponse

router = APIRouter(prefix="/api/stores/{store_id}/products", tags=["products"])


@router.get("", response_model=list[ProductResponse])
async def list_products(store_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product)
        .where(Product.store_id == store_id)
        .options(selectinload(Product.variants))
    )
    return result.scalars().all()


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

    filepath = None
    image_url = None
    if image:
        import io
        from PIL import Image, UnidentifiedImageError, ImageOps
        import pillow_heif
        try:
            pillow_heif.register_heif_opener()
            pillow_heif.register_avif_opener()
        except AttributeError:
            pass
        
        try:
            content = await image.read()
            if len(content) > 5 * 1024 * 1024:
                raise ValueError("Image size exceeds 5MB limit.")
            
            img = Image.open(io.BytesIO(content))
            img = ImageOps.exif_transpose(img)
            
            # Convert to RGB (JPEG doesn't support alpha channel)
            if img.mode in ('RGBA', 'P', 'LA') or getattr(img, 'format', '') in ('AVIF', 'HEIF', 'WEBP', 'PNG'):
                img = img.convert('RGB')
                
            # Resize if too large
            img.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            
            UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")))
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            
            filename = f"{uuid.uuid4()}.jpg"
            filepath = os.path.join(UPLOAD_DIR, filename)
            img.save(filepath, "JPEG", quality=85, optimize=True)
            
            image_url = f"/uploads/{filename}"
        except UnidentifiedImageError:
            raise HTTPException(status_code=400, detail="Unsupported image format or corrupted file.")
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Image processing failed: {str(e)}")

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
    except Exception as e:
        await db.rollback()
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except Exception:
                pass
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

    await db.delete(product)
    await db.commit()
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
