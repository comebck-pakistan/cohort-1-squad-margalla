"""Test fixtures for the backend test suite."""
import asyncio
import pytest
import pytest_asyncio
from app.database import init_db, create_tables, drop_tables
from app.models import (
    Store, Product, ProductAlias, ProductVariant, StorePolicy
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create test database engine."""
    engine, factory = init_db("sqlite+aiosqlite:///:memory:")
    await create_tables(engine)
    yield engine, factory
    await drop_tables(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Create a fresh DB session for each test."""
    engine, factory = db_engine
    async with factory() as session:
        yield session
        await session.rollback()


def make_fashion_store() -> Store:
    """Create fashion store object (no DB)."""
    return Store(
        id="test-store-fashion",
        business_name="Test Fashion House",
        owner_name="Test Owner",
        preferred_language="roman_urdu",
        ai_enabled=True,
    )


def make_shoe_store() -> Store:
    """Create shoe store object (no DB)."""
    return Store(
        id="test-store-shoes",
        business_name="Test Shoe Store",
        owner_name="Test Owner 2",
        preferred_language="english",
        ai_enabled=True,
    )


def make_fashion_products() -> list[Product]:
    """Create fashion products with variants and aliases (no DB)."""
    p1 = Product(
        id="prod-kurta-001",
        store_id="test-store-fashion",
        name="Women's Embroidered Kurta",
        category="kurta",
        sku="WEK-001",
        base_price=2500.0,
        is_active=True,
    )
    p1.aliases = [
        ProductAlias(product_id="prod-kurta-001", alias="embroidered kurta"),
        ProductAlias(product_id="prod-kurta-001", alias="kurta"),
        ProductAlias(product_id="prod-kurta-001", alias="ladies kurta"),
    ]
    p1.variants = [
        ProductVariant(id="var-sb-m", product_id="prod-kurta-001", color="sky blue", size="medium", price=2500.0, stock=4, sku="WEK-001-SB-M", is_active=True),
        ProductVariant(id="var-sb-l", product_id="prod-kurta-001", color="sky blue", size="large", price=2500.0, stock=0, sku="WEK-001-SB-L", is_active=True),
        ProductVariant(id="var-ow-m", product_id="prod-kurta-001", color="off white", size="medium", price=2700.0, stock=7, sku="WEK-001-OW-M", is_active=True),
        ProductVariant(id="var-ow-l", product_id="prod-kurta-001", color="off white", size="large", price=2700.0, stock=3, sku="WEK-001-OW-L", is_active=True),
        ProductVariant(id="var-mr-m", product_id="prod-kurta-001", color="maroon", size="medium", price=2600.0, stock=5, sku="WEK-001-MR-M", is_active=True),
    ]

    p2 = Product(
        id="prod-sk-001",
        store_id="test-store-fashion",
        name="Men's Classic Shalwar Kameez",
        category="shalwar kameez",
        sku="MSK-001",
        base_price=3200.0,
        is_active=True,
    )
    p2.aliases = [
        ProductAlias(product_id="prod-sk-001", alias="shalwar kameez"),
        ProductAlias(product_id="prod-sk-001", alias="kameez"),
    ]
    p2.variants = [
        ProductVariant(id="var-sk-wh-m", product_id="prod-sk-001", color="white", size="medium", price=3200.0, stock=10, is_active=True),
        ProductVariant(id="var-sk-bl-m", product_id="prod-sk-001", color="black", size="medium", price=3400.0, stock=3, is_active=True),
        ProductVariant(id="var-sk-bl-l", product_id="prod-sk-001", color="black", size="large", price=3400.0, stock=8, is_active=True),
    ]

    p3 = Product(
        id="prod-wc-001",
        store_id="test-store-fashion",
        name="Men's Embroidered Waistcoat",
        category="waistcoat",
        sku="MWC-001",
        base_price=1800.0,
        is_active=True,
    )
    p3.aliases = [
        ProductAlias(product_id="prod-wc-001", alias="waistcoat"),
        ProductAlias(product_id="prod-wc-001", alias="vest"),
    ]
    p3.variants = [
        ProductVariant(id="var-wc-nv-m", product_id="prod-wc-001", color="navy blue", size="medium", price=1800.0, stock=6, is_active=True),
    ]

    return [p1, p2, p3]


def make_shoe_products() -> list[Product]:
    """Create shoe products (no DB)."""
    s1 = Product(
        id="prod-snk-casual-001",
        store_id="test-store-shoes",
        name="Casual Black Sneakers",
        category="sneakers",
        sku="CBS-001",
        base_price=4500.0,
        is_active=True,
    )
    s1.aliases = [
        ProductAlias(product_id="prod-snk-casual-001", alias="casual sneakers"),
        ProductAlias(product_id="prod-snk-casual-001", alias="black sneakers"),
    ]
    s1.variants = [
        ProductVariant(id="var-s01-bl-40", product_id="prod-snk-casual-001", color="black", size="40", price=4500.0, stock=5, is_active=True),
        ProductVariant(id="var-s01-bl-42", product_id="prod-snk-casual-001", color="black", size="42", price=4500.0, stock=3, is_active=True),
        ProductVariant(id="var-s01-bl-44", product_id="prod-snk-casual-001", color="black", size="44", price=4500.0, stock=0, is_active=True),
    ]

    s2 = Product(
        id="prod-snk-run-001",
        store_id="test-store-shoes",
        name="Running Black Sneakers",
        category="sneakers",
        sku="RBS-001",
        base_price=6500.0,
        is_active=True,
    )
    s2.aliases = [
        ProductAlias(product_id="prod-snk-run-001", alias="running sneakers"),
        ProductAlias(product_id="prod-snk-run-001", alias="running shoes"),
    ]
    s2.variants = [
        ProductVariant(id="var-s02-bl-42", product_id="prod-snk-run-001", color="black", size="42", price=6500.0, stock=7, is_active=True),
        ProductVariant(id="var-s02-nv-42", product_id="prod-snk-run-001", color="navy blue", size="42", price=6800.0, stock=2, is_active=True),
    ]

    s3 = Product(
        id="prod-snk-leather-001",
        store_id="test-store-shoes",
        name="Leather Black Sneakers",
        category="sneakers",
        sku="LBS-001",
        base_price=8500.0,
        is_active=True,
    )
    s3.aliases = [
        ProductAlias(product_id="prod-snk-leather-001", alias="leather sneakers"),
    ]
    s3.variants = [
        ProductVariant(id="var-s03-bl-42", product_id="prod-snk-leather-001", color="black", size="42", price=8500.0, stock=5, is_active=True),
    ]

    return [s1, s2, s3]


def make_fashion_policies() -> list[StorePolicy]:
    """Create fashion store policies."""
    return [
        StorePolicy(store_id="test-store-fashion", policy_type="cod", policy_value="Haan, Cash on Delivery available hai."),
        StorePolicy(store_id="test-store-fashion", policy_type="delivery", policy_value="Delivery 3-5 working days mein hoti hai."),
        StorePolicy(store_id="test-store-fashion", policy_type="delivery_charges", policy_value="Rs. 200 delivery charges."),
        StorePolicy(store_id="test-store-fashion", policy_type="returns", policy_value="7 din ke andar return ho sakti hai."),
        StorePolicy(store_id="test-store-fashion", policy_type="exchange", policy_value="Size exchange 7 din ke andar."),
    ]


def make_shoe_policies() -> list[StorePolicy]:
    """Create shoe store policies."""
    return [
        StorePolicy(store_id="test-store-shoes", policy_type="cod", policy_value="Yes, COD is available."),
        StorePolicy(store_id="test-store-shoes", policy_type="delivery", policy_value="Delivery takes 3-7 business days."),
    ]
