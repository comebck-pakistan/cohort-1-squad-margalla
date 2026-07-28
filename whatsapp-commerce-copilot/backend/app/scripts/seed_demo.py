"""Seed demo stores, products, variants, aliases, and policies.

Two stores:
1. demo-store-fashion — Pakistani fashion (kurtas, shalwar kameez, etc.)
2. demo-store-shoes — Footwear store (sneakers, loafers, etc.)

Run: python -m app.scripts.seed_demo
"""
import asyncio
import sys
import os

# Add backend dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.database import init_db, create_tables, get_db_session_factory
from app.models import (
    Store, Product, ProductAlias, ProductVariant, StorePolicy, Customer
)


async def seed_demo(session):
    """Seed demo data into a given session (for testing and CLI)."""
    from sqlalchemy import select

    # Check if already seeded
    existing = await session.execute(select(Store).where(Store.id == "demo-store-fashion"))
    if existing.scalar_one_or_none():
        print("Demo data already seeded. Skipping.")
        return

    # ============================================================
    # STORE 1: Fashion Store
    # ============================================================
    fashion_store = Store(
        id="demo-store-fashion",
        business_name="Noor Fashion House",
        owner_name="Noor Ahmed",
        owner_phone="923001111111",
        owner_email="noor@example.com",
        preferred_language="roman_urdu",
        ai_enabled=True,
        whatsapp_status="disconnected",
    )
    session.add(fashion_store)

    # --- Fashion Products ---
    # Product 1: Women's Embroidered Kurta
    p1 = Product(
        id="prod-kurta-emb-001",
        store_id="demo-store-fashion",
        name="Women's Embroidered Kurta",
        category="kurta",
        sku="WEK-001",
        description="Premium cotton embroidered kurta with intricate threadwork",
        base_price=2500.0,
        is_active=True,
    )
    session.add(p1)
    session.add_all([
        ProductAlias(product_id="prod-kurta-emb-001", alias="embroidered kurta"),
        ProductAlias(product_id="prod-kurta-emb-001", alias="kurta"),
        ProductAlias(product_id="prod-kurta-emb-001", alias="ladies kurta"),
        ProductAlias(product_id="prod-kurta-emb-001", alias="women kurta"),
    ])
    session.add_all([
        ProductVariant(id="var-001-sb-m", product_id="prod-kurta-emb-001", color="sky blue", size="medium", price=2500.0, stock=4, sku="WEK-001-SB-M"),
        ProductVariant(id="var-001-sb-l", product_id="prod-kurta-emb-001", color="sky blue", size="large", price=2500.0, stock=0, sku="WEK-001-SB-L"),
        ProductVariant(id="var-001-ow-m", product_id="prod-kurta-emb-001", color="off white", size="medium", price=2700.0, stock=7, sku="WEK-001-OW-M"),
        ProductVariant(id="var-001-ow-l", product_id="prod-kurta-emb-001", color="off white", size="large", price=2700.0, stock=3, sku="WEK-001-OW-L"),
        ProductVariant(id="var-001-mr-m", product_id="prod-kurta-emb-001", color="maroon", size="medium", price=2600.0, stock=5, sku="WEK-001-MR-M"),
        ProductVariant(id="var-001-mr-s", product_id="prod-kurta-emb-001", color="maroon", size="small", price=2600.0, stock=2, sku="WEK-001-MR-S"),
    ])

    # Product 2: Men's Shalwar Kameez
    p2 = Product(
        id="prod-sk-001",
        store_id="demo-store-fashion",
        name="Men's Classic Shalwar Kameez",
        category="shalwar kameez",
        sku="MSK-001",
        description="Premium cotton shalwar kameez for men",
        base_price=3200.0,
        is_active=True,
    )
    session.add(p2)
    session.add_all([
        ProductAlias(product_id="prod-sk-001", alias="shalwar kameez"),
        ProductAlias(product_id="prod-sk-001", alias="kameez"),
        ProductAlias(product_id="prod-sk-001", alias="suit"),
    ])
    session.add_all([
        ProductVariant(id="var-002-wh-m", product_id="prod-sk-001", color="white", size="medium", price=3200.0, stock=10, sku="MSK-001-WH-M"),
        ProductVariant(id="var-002-wh-l", product_id="prod-sk-001", color="white", size="large", price=3200.0, stock=6, sku="MSK-001-WH-L"),
        ProductVariant(id="var-002-bl-m", product_id="prod-sk-001", color="black", size="medium", price=3400.0, stock=3, sku="MSK-001-BL-M"),
        ProductVariant(id="var-002-bl-l", product_id="prod-sk-001", color="black", size="large", price=3400.0, stock=8, sku="MSK-001-BL-L"),
    ])

    # Product 3: Women's Printed Lawn Suit
    p3 = Product(
        id="prod-lawn-001",
        store_id="demo-store-fashion",
        name="Women's Printed Lawn Suit",
        category="lawn suit",
        sku="WLS-001",
        description="3-piece printed lawn suit with dupatta",
        base_price=4500.0,
        is_active=True,
    )
    session.add(p3)
    session.add_all([
        ProductAlias(product_id="prod-lawn-001", alias="lawn suit"),
        ProductAlias(product_id="prod-lawn-001", alias="lawn"),
        ProductAlias(product_id="prod-lawn-001", alias="3 piece suit"),
        ProductAlias(product_id="prod-lawn-001", alias="printed suit"),
    ])
    session.add_all([
        ProductVariant(id="var-003-pk-m", product_id="prod-lawn-001", color="pink", size="medium", price=4500.0, stock=5, sku="WLS-001-PK-M"),
        ProductVariant(id="var-003-pk-l", product_id="prod-lawn-001", color="pink", size="large", price=4500.0, stock=2, sku="WLS-001-PK-L"),
        ProductVariant(id="var-003-gr-m", product_id="prod-lawn-001", color="green", size="medium", price=4500.0, stock=8, sku="WLS-001-GR-M"),
    ])

    # Product 4: Men's Waistcoat
    p4 = Product(
        id="prod-wc-001",
        store_id="demo-store-fashion",
        name="Men's Embroidered Waistcoat",
        category="waistcoat",
        sku="MWC-001",
        description="Formal embroidered waistcoat",
        base_price=1800.0,
        is_active=True,
    )
    session.add(p4)
    session.add_all([
        ProductAlias(product_id="prod-wc-001", alias="waistcoat"),
        ProductAlias(product_id="prod-wc-001", alias="vest"),
        ProductAlias(product_id="prod-wc-001", alias="sadri"),
    ])
    session.add_all([
        ProductVariant(id="var-004-nv-m", product_id="prod-wc-001", color="navy blue", size="medium", price=1800.0, stock=6, sku="MWC-001-NV-M"),
        ProductVariant(id="var-004-nv-l", product_id="prod-wc-001", color="navy blue", size="large", price=1800.0, stock=4, sku="MWC-001-NV-L"),
        ProductVariant(id="var-004-gd-m", product_id="prod-wc-001", color="golden", size="medium", price=2000.0, stock=3, sku="MWC-001-GD-M"),
    ])

    # --- Fashion Policies ---
    session.add_all([
        StorePolicy(store_id="demo-store-fashion", policy_type="cod", policy_value="Haan, Cash on Delivery (COD) available hai puri Pakistan mein."),
        StorePolicy(store_id="demo-store-fashion", policy_type="delivery", policy_value="Delivery 3-5 working days mein hoti hai. Major cities mein 2-3 din."),
        StorePolicy(store_id="demo-store-fashion", policy_type="delivery_charges", policy_value="Delivery charges Rs. 200 hain. Rs. 5000 se zyada order pe free delivery."),
        StorePolicy(store_id="demo-store-fashion", policy_type="returns", policy_value="7 din ke andar return ho sakti hai agar product unused aur original packaging mein ho."),
        StorePolicy(store_id="demo-store-fashion", policy_type="exchange", policy_value="Size exchange 7 din ke andar available hai. Color exchange nahi hoti."),
        StorePolicy(store_id="demo-store-fashion", policy_type="delivery_locations", policy_value="Pakistan ke tamam major cities mein delivery available hai."),
    ])

    # ============================================================
    # STORE 2: Shoe Store
    # ============================================================
    shoe_store = Store(
        id="demo-store-shoes",
        business_name="StepUp Footwear",
        owner_name="Ali Hassan",
        owner_phone="923002222222",
        owner_email="ali@example.com",
        preferred_language="english",
        ai_enabled=True,
        whatsapp_status="disconnected",
    )
    session.add(shoe_store)

    # --- Shoe Products ---
    # Product 1: Black Sneakers
    s1 = Product(
        id="prod-snk-casual-001",
        store_id="demo-store-shoes",
        name="Casual Black Sneakers",
        category="sneakers",
        sku="CBS-001",
        description="Casual everyday black sneakers with cushioned sole",
        base_price=4500.0,
        is_active=True,
    )
    session.add(s1)
    session.add_all([
        ProductAlias(product_id="prod-snk-casual-001", alias="casual sneakers"),
        ProductAlias(product_id="prod-snk-casual-001", alias="black sneakers"),
    ])
    session.add_all([
        ProductVariant(id="var-s01-bl-40", product_id="prod-snk-casual-001", color="black", size="40", price=4500.0, stock=5, sku="CBS-001-BL-40"),
        ProductVariant(id="var-s01-bl-42", product_id="prod-snk-casual-001", color="black", size="42", price=4500.0, stock=3, sku="CBS-001-BL-42"),
        ProductVariant(id="var-s01-bl-44", product_id="prod-snk-casual-001", color="black", size="44", price=4500.0, stock=0, sku="CBS-001-BL-44"),
    ])

    # Product 2: Running Sneakers
    s2 = Product(
        id="prod-snk-run-001",
        store_id="demo-store-shoes",
        name="Running Black Sneakers",
        category="sneakers",
        sku="RBS-001",
        description="Professional running shoes with advanced cushioning",
        base_price=6500.0,
        is_active=True,
    )
    session.add(s2)
    session.add_all([
        ProductAlias(product_id="prod-snk-run-001", alias="running sneakers"),
        ProductAlias(product_id="prod-snk-run-001", alias="running shoes"),
    ])
    session.add_all([
        ProductVariant(id="var-s02-bl-40", product_id="prod-snk-run-001", color="black", size="40", price=6500.0, stock=4, sku="RBS-001-BL-40"),
        ProductVariant(id="var-s02-bl-42", product_id="prod-snk-run-001", color="black", size="42", price=6500.0, stock=7, sku="RBS-001-BL-42"),
        ProductVariant(id="var-s02-nv-42", product_id="prod-snk-run-001", color="navy blue", size="42", price=6800.0, stock=2, sku="RBS-001-NV-42"),
    ])

    # Product 3: Leather Sneakers
    s3 = Product(
        id="prod-snk-leather-001",
        store_id="demo-store-shoes",
        name="Leather Black Sneakers",
        category="sneakers",
        sku="LBS-001",
        description="Premium leather sneakers for formal-casual wear",
        base_price=8500.0,
        is_active=True,
    )
    session.add(s3)
    session.add_all([
        ProductAlias(product_id="prod-snk-leather-001", alias="leather sneakers"),
        ProductAlias(product_id="prod-snk-leather-001", alias="leather shoes"),
    ])
    session.add_all([
        ProductVariant(id="var-s03-bl-40", product_id="prod-snk-leather-001", color="black", size="40", price=8500.0, stock=2, sku="LBS-001-BL-40"),
        ProductVariant(id="var-s03-bl-42", product_id="prod-snk-leather-001", color="black", size="42", price=8500.0, stock=5, sku="LBS-001-BL-42"),
        ProductVariant(id="var-s03-br-42", product_id="prod-snk-leather-001", color="brown", size="42", price=8500.0, stock=3, sku="LBS-001-BR-42"),
    ])

    # Product 4: Classic Loafers
    s4 = Product(
        id="prod-loafer-001",
        store_id="demo-store-shoes",
        name="Classic Brown Loafers",
        category="loafers",
        sku="CBL-001",
        description="Classic leather loafers for formal wear",
        base_price=5500.0,
        is_active=True,
    )
    session.add(s4)
    session.add_all([
        ProductAlias(product_id="prod-loafer-001", alias="loafers"),
        ProductAlias(product_id="prod-loafer-001", alias="brown loafers"),
        ProductAlias(product_id="prod-loafer-001", alias="formal shoes"),
    ])
    session.add_all([
        ProductVariant(id="var-s04-br-40", product_id="prod-loafer-001", color="brown", size="40", price=5500.0, stock=4, sku="CBL-001-BR-40"),
        ProductVariant(id="var-s04-br-42", product_id="prod-loafer-001", color="brown", size="42", price=5500.0, stock=6, sku="CBL-001-BR-42"),
        ProductVariant(id="var-s04-tn-42", product_id="prod-loafer-001", color="tan", size="42", price=5800.0, stock=2, sku="CBL-001-TN-42"),
    ])

    # --- Shoe Policies ---
    session.add_all([
        StorePolicy(store_id="demo-store-shoes", policy_type="cod", policy_value="Yes, Cash on Delivery is available across Pakistan."),
        StorePolicy(store_id="demo-store-shoes", policy_type="delivery", policy_value="Delivery takes 3-7 business days. Express delivery available for major cities (2-3 days)."),
        StorePolicy(store_id="demo-store-shoes", policy_type="delivery_charges", policy_value="Delivery charges are Rs. 250. Free delivery on orders above Rs. 8000."),
        StorePolicy(store_id="demo-store-shoes", policy_type="returns", policy_value="Returns accepted within 14 days if product is unworn with original box."),
        StorePolicy(store_id="demo-store-shoes", policy_type="exchange", policy_value="Size exchange available within 14 days. One free exchange per order."),
        StorePolicy(store_id="demo-store-shoes", policy_type="delivery_locations", policy_value="We deliver to all major cities in Pakistan. Remote areas may take 5-10 days."),
    ])

    print("Demo data seeded successfully!")
    print(f"  Fashion store: demo-store-fashion ({fashion_store.business_name})")
    print(f"    Products: 4 (kurta, shalwar kameez, lawn suit, waistcoat)")
    print(f"  Shoe store: demo-store-shoes ({shoe_store.business_name})")
    print(f"    Products: 4 (casual sneakers, running sneakers, leather sneakers, loafers)")


async def seed():
    """Seed demo data into the database."""
    # Use SQLite for local dev
    db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./dev.db")
    engine, factory = init_db(db_url)

    # Create tables
    await create_tables(engine)

    async with factory() as session:
        await seed_demo(session)
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
