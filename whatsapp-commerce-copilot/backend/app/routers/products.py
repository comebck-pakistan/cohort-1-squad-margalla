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

    image_url = None
    if image:
        # Save image to local uploads directory
        file_extension = image.filename.split(".")[-1] if "." in image.filename else "jpg"
        filename = f"{uuid.uuid4()}.{file_extension}"
        filepath = os.path.join("uploads", filename)
        
        with open(filepath, "wb") as f:
            f.write(await image.read())
            
        # The backend URL is accessible via BACKEND_URL env var, or relative path
        # In this docker setup, the dashboard accesses the backend via gateway or directly via localhost:8000
        # We will store the relative URL path and the frontend/gateway can resolve it
        image_url = f"/uploads/{filename}"

    # Create product
    new_product = Product(
        store_id=store_id,
        name=name,
        category=category,
        description=description,
        base_price=price,
        image_url=image_url
    )
    db.add(new_product)
    
    # Needs to be flushed to get the product ID
    await db.flush()

    # Add default variant
    variant = ProductVariant(
        product_id=new_product.id,
        price=price,
        stock=stock,
    )
    db.add(variant)

    # Add aliases from labels
    if labels:
        label_list = [label.strip() for label in labels.split(",") if label.strip()]
        for label in label_list:
            alias = ProductAlias(
                product_id=new_product.id,
                alias=label
            )
            db.add(alias)

    await db.commit()
    
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
