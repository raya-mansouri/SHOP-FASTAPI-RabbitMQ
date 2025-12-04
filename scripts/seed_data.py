"""
Database seeding script.

Run with: python -m scripts.seed_data
"""

import asyncio
from decimal import Decimal

from app.infrastructure.database import (
    AsyncSessionLocal,
    ProductModel,
    init_db,
    close_db,
)


async def seed_products():
    """Seed initial product data."""
    
    products = [
        ProductModel(name="Laptop", price=Decimal("99900"), stock=50),
        ProductModel(name="Mouse", price=Decimal("2900"), stock=200),
        ProductModel(name="Keyboard", price=Decimal("79000"), stock=150),
        ProductModel(name="Monitor", price=Decimal("29900"), stock=75),
        ProductModel(name="Headphones", price=Decimal("14900"), stock=100),
        ProductModel(name="USB Cable", price=Decimal("9000"), stock=500),
        ProductModel(name="Webcam", price=Decimal("69000"), stock=80),
        ProductModel(name="Desk Lamp", price=Decimal("39000"), stock=120),
    ]
    
    async with AsyncSessionLocal() as session:
        # Check if products exist
        from sqlalchemy import select
        result = await session.execute(select(ProductModel).limit(1))
        if result.scalar_one_or_none():
            print("Products already seeded, skipping...")
            return
        
        session.add_all(products)
        await session.commit()
        print(f"Seeded {len(products)} products")


async def main():
    """Run seeding."""
    print("Initializing database...")
    await init_db()
    
    print("Seeding products...")
    await seed_products()
    
    print("Closing connections...")
    await close_db()
    
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())