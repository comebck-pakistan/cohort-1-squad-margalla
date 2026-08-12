import asyncio
import httpx
import uuid
import os

async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        with open("test.avif", "rb") as f:
            files = {"image": ("test.avif", f, "image/avif")}
            data = {
                "name": "Test Product",
                "price": "100.0",
                "stock": "10"
            }
            resp = await client.post("/api/stores/demo-store-fashion/products", data=data, files=files)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")

asyncio.run(main())
