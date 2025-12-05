"""
Product Service - Application Layer.

RESPONSIBILITY: Orchestrates product-related use cases
  - Get products (with caching)
  - Get single product
  - Validate product availability

DECISION: Service layer between API and Repository
WHY:
  - Business logic stays out of API routes
  - Can add caching, logging, metrics in one place
  - Easy to test business logic in isolation
"""

from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProductNotFoundError
from app.infrastructure.database.models import ProductModel
from app.infrastructure.database.repositories import ProductRepository
from app.api.schemas import (
    ProductResponse,
    ProductListResponse,
)


class ProductService:
    """
    Product service handles all product-related operations.
    
    PATTERN: Service takes repository as dependency
    WHY: Dependency injection for testability
    """
    
    def __init__(self, repository: ProductRepository):
        self.repository = repository
    
    async def get_all_products(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> ProductListResponse:
        """
        Get all products with pagination.
        
        DECISION: Return DTO, not ORM model
        WHY: Decouple API from database structure
        
        TODO: Add Redis caching here (next step)
        """
        products = await self.repository.get_all(skip=skip, limit=limit)
        
        # Convert to response schema
        items = [
            ProductResponse.model_validate(product)
            for product in products
        ]
        
        return ProductListResponse(
            items=items,
            total=len(items),  # TODO: Add count query for true total
            skip=skip,
            limit=limit
        )
    
    async def get_product_by_id(self, product_id: int) -> ProductResponse:
        """
        Get single product by ID.
        
        RAISES: ProductNotFoundError if not exists
        """
        product = await self.repository.get_by_id(product_id)
        
        if product is None:
            raise ProductNotFoundError(product_id)
        
        return ProductResponse.model_validate(product)
    
    async def get_products_by_ids(
        self,
        product_ids: List[int]
    ) -> List[ProductModel]:
        """
        Get multiple products by IDs.
        
        RETURNS: ORM models (for internal use by OrderService)
        
        DECISION: Return ORM models here, not DTOs
        WHY: OrderService needs to work with models for stock operations
        """
        return await self.repository.get_by_ids(product_ids)
    
    async def validate_products_exist(
        self,
        product_ids: List[int]
    ) -> dict[int, ProductModel]:
        """
        Validate all products exist and return them as dict.
        
        RAISES: ProductNotFoundError if any product missing
        
        RETURNS: Dict mapping product_id -> ProductModel
        """
        products = await self.repository.get_by_ids(product_ids)
        
        # Create lookup dict
        product_map = {p.id: p for p in products}
        
        # Check for missing products
        missing = set(product_ids) - set(product_map.keys())
        if missing:
            # Raise error for first missing product
            raise ProductNotFoundError(list(missing)[0])
        
        return product_map
    
    async def check_stock_availability(
        self,
        product_id: int,
        quantity: int
    ) -> bool:
        """
        Check if product has sufficient stock.
        
        DECISION: Simple check without locking
        WHY: For validation only, actual deduction uses locks
        """
        product = await self.repository.get_by_id(product_id)
        
        if product is None:
            raise ProductNotFoundError(product_id)
        
        return product.stock >= quantity


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_product_service(session: AsyncSession) -> ProductService:
    """
    Factory function to create ProductService.
    
    DECISION: Factory function instead of direct instantiation
    WHY: Encapsulates dependency creation
    """
    repository = ProductRepository(session)
    return ProductService(repository)
