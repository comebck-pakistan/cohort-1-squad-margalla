import pytest
from sqlalchemy import select
from app.models.product import Product, ProductVariant
from app.models.order import Order, OrderItem
from app.models.conversation import Conversation
from app.services.conversation_controller import ConversationController

from .conftest import make_fashion_store

@pytest.mark.asyncio
async def test_order_creation_success(db_session):
    """Test successful order creation decreases stock."""
    # Setup Store, Product and Variant
    store = make_fashion_store()
    db_session.add(store)
    await db_session.flush()

    p = Product(store_id=store.id, name="Test Product", is_active=True)
    db_session.add(p)
    await db_session.flush()

    v = ProductVariant(product_id=p.id, price=100.0, stock=5, is_active=True)
    db_session.add(v)
    await db_session.flush()

    conv = Conversation(store_id=store.id, customer_id="c1", status="active", order_stage="ORDER_CONFIRMATION", quantity=2)
    db_session.add(conv)
    await db_session.flush()

    # Reload product with variants
    from sqlalchemy.orm import selectinload
    p = (await db_session.execute(select(Product).where(Product.id == p.id).options(selectinload(Product.variants)))).scalar_one()

    controller = ConversationController()
    
    from app.services.response_builder import ProcessedResponse
    response = ProcessedResponse(
        message="",
        intent="order_confirmation",
        confidence=1.0,
        store_id=store.id,
        customer_number="123"
    )
    
    # We also need to set conversation.current_product_id and current_variant_id
    conv.current_product_id = p.id
    conv.current_variant_id = v.id
    class MockEntities:
        def __init__(self):
            self.quantity = None
            self.size = None
            self.color = None
            self.delivery_city = None
    entities = MockEntities()
    
    res = await controller._advance_order(
        db_session, conv, "yes", "order_confirmation", entities, response, [p], "en", "123"
    )
    
    assert "confirmed" in res.message.lower() or "confirmed" in res.message.lower()
    
    # Check variant stock
    await db_session.refresh(v)
    assert v.stock == 3
    
    # Check order
    orders = (await db_session.execute(select(Order))).scalars().all()
    assert len(orders) == 1
    assert orders[0].total_amount == 200.0

@pytest.mark.asyncio
async def test_order_creation_insufficient_stock(db_session):
    """Test order creation fails gracefully when stock is insufficient."""
    store = make_fashion_store()
    db_session.add(store)
    await db_session.flush()

    p = Product(store_id=store.id, name="Test Product", is_active=True)
    db_session.add(p)
    await db_session.flush()

    v = ProductVariant(product_id=p.id, price=100.0, stock=1, is_active=True) # Only 1 in stock
    db_session.add(v)
    await db_session.flush()

    conv = Conversation(store_id=store.id, customer_id="c1", status="active", order_stage="ORDER_CONFIRMATION", quantity=2)
    db_session.add(conv)
    await db_session.flush()

    from sqlalchemy.orm import selectinload
    p = (await db_session.execute(select(Product).where(Product.id == p.id).options(selectinload(Product.variants)))).scalar_one()

    controller = ConversationController()
    from app.services.response_builder import ProcessedResponse
    response = ProcessedResponse(
        message="",
        intent="order_confirmation",
        confidence=1.0,
        store_id=store.id,
        customer_number="123"
    )
    
    conv.current_product_id = p.id
    conv.current_variant_id = v.id
    
    class MockEntities:
        def __init__(self):
            self.quantity = None
            self.size = None
            self.color = None
            self.delivery_city = None
    entities = MockEntities()
    
    # Should fail
    res = await controller._advance_order(
        db_session, conv, "yes", "order_confirmation", entities, response, [p], "en", "123"
    )
    assert "available" in res.message.lower() or "out of stock" in res.message.lower()
    
    await db_session.refresh(v)
    assert v.stock == 1 # Stock unchanged
    
    orders = (await db_session.execute(select(Order))).scalars().all()
    assert len(orders) == 0

@pytest.mark.asyncio
async def test_order_creation_inactive_variant(db_session):
    """Test order creation fails if variant is inactive."""
    store = make_fashion_store()
    db_session.add(store)
    await db_session.flush()

    p = Product(store_id=store.id, name="Test Product", is_active=True)
    db_session.add(p)
    await db_session.flush()

    v = ProductVariant(product_id=p.id, price=100.0, stock=10, is_active=False)
    db_session.add(v)
    await db_session.flush()

    conv = Conversation(store_id=store.id, customer_id="c1", status="active", order_stage="ORDER_CONFIRMATION", quantity=1)
    db_session.add(conv)
    await db_session.flush()

    from sqlalchemy.orm import selectinload
    p = (await db_session.execute(select(Product).where(Product.id == p.id).options(selectinload(Product.variants)))).scalar_one()

    controller = ConversationController()
    from app.services.response_builder import ProcessedResponse
    response = ProcessedResponse(
        message="",
        intent="order_confirmation",
        confidence=1.0,
        store_id=store.id,
        customer_number="123"
    )
    
    conv.current_product_id = p.id
    conv.current_variant_id = v.id
    
    class MockEntities:
        def __init__(self):
            self.quantity = None
            self.size = None
            self.color = None
            self.delivery_city = None
    entities = MockEntities()
    
    res = await controller._advance_order(
        db_session, conv, "yes", "order_confirmation", entities, response, [p], "en", "123"
    )
    
    assert "no longer available" in res.message.lower()
