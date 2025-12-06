# app/api/routes/products.py
"""
Product API Routes.

ENDPOINTS:
- GET /products - List all products with pagination
- GET /products/{id} - Get single product by ID
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db_session
from app.infrastructure.cache import get_cache_service, CacheService
from app.application.queries import GetProductsQuery, GetProductByIdQuery
from app.api.schemas import ProductResponse, ProductListResponse

router = APIRouter()


# Type aliases for cleaner dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
Cache = Annotated[CacheService, Depends(get_cache_service)]


@router.get("", response_model=ProductListResponse)
async def list_products(
    db: DbSession,
    cache: Cache,
    skip: int = Query(default=0, ge=0, description="Number of items to skip"),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of items to return"),
):
    """
    Get list of products with pagination.
    
    - **skip**: Number of products to skip (default: 0)
    - **limit**: Maximum number of products to return (default: 100, max: 1000)
    """
    query = GetProductsQuery(
        session=db,
        cache=cache,
        skip=skip,
        limit=limit,
    )
    return await query.execute()


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: DbSession,
    cache: Cache,
):
    """
    Get a single product by ID.
    
    - **product_id**: The ID of the product to retrieve
    """
    query = GetProductByIdQuery(
        product_id=product_id,
        session=db,
        cache=cache,
    )
    result = await query.execute()
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with id {product_id} not found",
        )
    
    return result
