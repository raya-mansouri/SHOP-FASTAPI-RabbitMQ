"""
Repository Interfaces (Ports).

DECISION: Using Protocol for repository interfaces
WHY: 
  - Dependency Inversion Principle
  - Easy to swap implementations (testing, different DBs)
  - Clear contracts for data access
  
ALTERNATIVE: Abstract Base Classes (ABC)
  - More explicit but heavier
  - Protocol is more Pythonic for duck typing
"""

from abc import abstractmethod
from typing import Protocol, List, Optional
from uuid import UUID

from app.infrastructure.database.models.order import OrderModel, OrderStatus
from app.infrastructure.database.models.product import ProductModel


class ProductRepositoryProtocol(Protocol):
    """Interface for product data access."""
    
    @abstractmethod
    async def get_by_id(self, product_id: int) -> Optional["ProductModel"]:
        """Get product by ID."""
        ...
    
    @abstractmethod
    async def get_by_ids(self, product_ids: List[int]) -> List["ProductModel"]:
        """Get multiple products by IDs."""
        ...
    
    @abstractmethod
    async def get_all(self, skip: int = 0, limit: int = 100) -> List["ProductModel"]:
        """Get all products with pagination."""
        ...
    
    @abstractmethod
    async def get_by_id_for_update(self, product_id: int) -> Optional["ProductModel"]:
        """Get product with row lock for update."""
        ...
    
    @abstractmethod
    async def update_stock(
        self, 
        product_id: int, 
        quantity_delta: int,
        expected_version: int
    ) -> bool:
        """
        Update stock with optimistic locking.
        Returns True if update succeeded.
        """
        ...


class OrderRepositoryProtocol(Protocol):
    """Interface for order data access."""
    
    @abstractmethod
    async def create(self, order: "OrderModel") -> "OrderModel":
        """Create new order."""
        ...
    
    @abstractmethod
    async def get_by_id(self, order_id: UUID) -> Optional["OrderModel"]:
        """Get order by ID with items."""
        ...
    
    @abstractmethod
    async def get_by_id_for_update(self, order_id: UUID) -> Optional["OrderModel"]:
        """Get order with row lock."""
        ...
    
    @abstractmethod
    async def get_by_user(
        self, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 20
    ) -> List["OrderModel"]:
        """Get orders for a user."""
        ...
    
    @abstractmethod
    async def update_status(
        self,
        order_id: UUID,
        new_status: "OrderStatus",
        expected_version: int,
        failure_reason: Optional[str] = None
    ) -> bool:
        """Update order status with optimistic locking."""
        ...
    
    @abstractmethod
    async def get_by_idempotency_key(self, key: str) -> Optional["OrderModel"]:
        """Find order by idempotency key."""
        ...