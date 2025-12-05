"""
Get Products Queries.

READ PATH: Redis -> PostgreSQL

CACHING STRATEGY:
- Product list: Cached for 5 minutes
- Single product: Cached for 5 minutes
- Cache invalidated on stock change
"""

from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.queries.base import Query
from app.api.schemas import ProductResponse, ProductListResponse
from app.infrastructure.database.repositories import ProductRepository
from app.infrastructure.cache import CacheService, CacheKeys


class GetProductsQuery(Query[ProductListResponse]):
    """
    Query to get paginated list of products.
    
    READ PATH:
    1. Check Redis cache
    2. If miss, query PostgreSQL
    3. Cache result in Redis
    4. Return data
    """
    
    def __init__(
        self,
        session: AsyncSession,
        cache: CacheService,
        skip: int = 0,
        limit: int = 100
    ):
        self.session = session
        self.cache = cache
        self.skip = skip
        self.limit = limit
        self.repository = ProductRepository(session)
    
    async def execute(self) -> ProductListResponse:
        """Execute query with caching."""
        cache_key = CacheKeys.product_list(self.skip, self.limit)
        
        # 1. Try cache first
        cached = await self.cache.get_model(cache_key, ProductListResponse)
        if cached is not None:
            return cached
        
        # 2. Cache miss - query database
        products = await self.repository.get_all(
            skip=self.skip, 
            limit=self.limit
        )
        
        # 3. Convert to response schema
        items = [
            ProductResponse(
                id=p.id,
                name=p.name,
                price=p.price,
                stock=p.stock,
                created_at=p.created_at,
                updated_at=p.updated_at
            )
            for p in products
        ]
        
        result = ProductListResponse(
            items=items,
            total=len(items),
            skip=self.skip,
            limit=self.limit
        )
        
        # 4. Store in cache
        await self.cache.set_model(
            cache_key, 
            result, 
            ttl=CacheKeys.TTL_MEDIUM
        )
        
        return result


class GetProductByIdQuery(Query[Optional[ProductResponse]]):
    """
    Query to get single product by ID.
    
    Returns None if not found (let API handle 404).
    """
    
    def __init__(
        self,
        product_id: int,
        session: AsyncSession,
        cache: CacheService
    ):
        self.product_id = product_id
        self.session = session
        self.cache = cache
        self.repository = ProductRepository(session)
    
    async def execute(self) -> Optional[ProductResponse]:
        """Execute query with caching."""
        cache_key = CacheKeys.product(self.product_id)
        
        # 1. Try cache
        cached = await self.cache.get_model(cache_key, ProductResponse)
        if cached is not None:
            return cached
        
        # 2. Cache miss - query database
        product = await self.repository.get_by_id(self.product_id)
        
        if product is None:
            return None
        
        # 3. Convert and cache
        result = ProductResponse(
            id=product.id,
            name=product.name,
            price=product.price,
            stock=product.stock,
            created_at=product.created_at,
            updated_at=product.updated_at
        )
        
        await self.cache.set_model(
            cache_key, 
            result, 
            ttl=CacheKeys.TTL_MEDIUM
        )
        
        return result