import asyncio
from app.models.product import Product
from app.services.catalog_search import CatalogSearchService

async def run():
    p1 = Product(id="1", name="Blue Kurta", base_price=10.0, is_active=True)
    p2 = Product(id="2", name="Red Kurta", base_price=20.0, is_active=True)
    
    searcher = CatalogSearchService()
    res = searcher.search([p1, p2], query="blue kurta")
    print(res.is_ambiguous)
    for m in res.matches:
        print(m.product.name, m.score, m.match_reason)

if __name__ == "__main__":
    asyncio.run(run())
