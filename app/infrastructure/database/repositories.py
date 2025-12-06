"""
Repository Implementations.

DECISION: Repository pattern with SQLAlchemy
WHY:
  - Encapsulates all SQL/ORM queries
  - Single place to optimize queries
  - Easy to test with mocks
  - Hides persistence details from services

PATTERN: Each repository handles one aggregate root
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.infrastructure.database.models import (
    OrderItemModel,
    OrderModel,
    OrderStatus,
    ProductModel,
)
from app.domain.exceptions import EntityNotFoundError


class ProductRepository:
    """
    Product data access repository.
    
    DECISION: Repository takes session in constructor
    WHY: 
      - Session lifecycle managed by caller (FastAPI dependency)
      - Same session for multiple operations (transaction)
    
    ALTERNATIVE: Session per method
      - More isolated but harder to do transactions
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, product_id: int) -> Optional[ProductModel]:
        """
        Get product by ID.
        
        Simple query, no locking.
        """
        query = select(ProductModel).where(ProductModel.id == product_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_ids(self, product_ids: List[int]) -> List[ProductModel]:
        """
        Get multiple products by IDs.
        
        DECISION: Using IN clause
        WHY: Single query vs N queries
        
        NOTE: For very large lists (1000+), consider chunking
        """
        if not product_ids:
            return []
        
        query = (
            select(ProductModel)
            .where(ProductModel.id.in_(product_ids))
            .order_by(ProductModel.id)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_all(
        self, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[ProductModel]:
        """
        Get all products with pagination.
        
        DECISION: Default limit of 100
        WHY: Prevent accidental full table scans
        """
        query = (
            select(ProductModel)
            .order_by(ProductModel.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def get_by_id_for_update(
        self, 
        product_id: int,
        nowait: bool = False
    ) -> Optional[ProductModel]:
        """
        Get product with row-level lock.
        
        CRITICAL: This is the key to preventing race conditions!
        
        SELECT ... FOR UPDATE locks the row until transaction commits.
        Other transactions trying to lock the same row will wait (or fail with nowait).
        
        DECISION: Using FOR UPDATE
        WHY: Pessimistic locking for stock updates
        
        ALTERNATIVE: Optimistic locking only
          - Pro: No blocking
          - Con: More retries under high contention
        
        We use BOTH: FOR UPDATE + version check for defense in depth.
        
        PARAMETERS:
          nowait: If True, raise error instead of waiting for lock
        """
        query = (
            select(ProductModel)
            .where(ProductModel.id == product_id)
            .with_for_update(nowait=nowait)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_ids_for_update(
        self,
        product_ids: List[int]
    ) -> List[ProductModel]:
        """
        Get multiple products with row locks.
        
        DECISION: Order by ID when locking multiple rows
        WHY: Prevents deadlocks! Always lock in consistent order.
        
        DEADLOCK EXAMPLE (without ordering):
          Transaction A: Lock product 1, then product 2
          Transaction B: Lock product 2, then product 1
          -> Deadlock!
        
        With ordering, both transactions lock 1 first, then 2.
        """
        if not product_ids:
            return []
        
        # Sort IDs to prevent deadlocks
        sorted_ids = sorted(product_ids)
        
        query = (
            select(ProductModel)
            .where(ProductModel.id.in_(sorted_ids))
            .order_by(ProductModel.id)  # CRITICAL: Consistent ordering
            .with_for_update()
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_stock(
        self,
        product_id: int,
        quantity_delta: int,
        expected_version: int
    ) -> bool:
        """
        Update stock with optimistic locking.
        
        DECISION: Atomic update with version check
        WHY: 
          - Detects concurrent modifications
          - Single query (atomic)
          - No race condition window
        
        PATTERN: Optimistic Locking
          1. Read row with version
          2. Update with WHERE version = expected
          3. If no rows updated, someone else modified it
        
        RETURNS: True if update succeeded, False if version mismatch
        """
        query = (
            update(ProductModel)
            .where(
                and_(
                    ProductModel.id == product_id,
                    ProductModel.version == expected_version,
                    # Also check stock won't go negative
                    ProductModel.stock + quantity_delta >= 0
                )
            )
            .values(
                stock=ProductModel.stock + quantity_delta,
                version=ProductModel.version + 1,
                updated_at=func.now()
            )
            .execution_options(synchronize_session=False)
        )
        
        result = await self.session.execute(query)
        
        # rowcount tells us if the update matched any rows
        return result.rowcount > 0
    
    async def deduct_stock(
        self,
        product_id: int,
        quantity: int
    ) -> ProductModel:
        """
        Deduct stock with pessimistic locking.

        CRITICAL: This is the key method for preventing race conditions!

        Steps:
        1. SELECT FOR UPDATE (locks the row)
        2. Check if sufficient stock
        3. Deduct stock atomically
        4. Return updated product

        DECISION: Pessimistic locking (SELECT FOR UPDATE)
        WHY:
          - Prevents race conditions completely
          - Simple and reliable
          - Works under high contention

        RAISES: InsufficientStockError if not enough stock
        """
        from app.domain.exceptions import InsufficientStockError

        # Step 1: Lock the row
        product = await self.get_by_id_for_update(product_id)
        if not product:
            raise EntityNotFoundError(f"Product {product_id} not found")

        # Step 2: Check stock
        if product.stock < quantity:
            raise InsufficientStockError(
                product_id=product.id,
                product_name=product.name,
                requested=quantity,
                available=product.stock
            )

        # Step 3: Deduct stock
        product.stock -= quantity
        product.version += 1
        product.updated_at = datetime.now(timezone.utc)

        # Flush to ensure constraints are checked
        await self.session.flush()

        return product

    async def deduct_stock_atomic(
        self,
        product_id: int,
        quantity: int
    ) -> bool:
        """
        Atomically deduct stock (alternative approach).
        
        DECISION: Single UPDATE with check
        WHY: Simpler than SELECT FOR UPDATE for single operations
        
        This doesn't need version locking because the check is atomic.
        The WHERE clause ensures stock >= quantity at execution time.
        """
        query = (
            update(ProductModel)
            .where(
                and_(
                    ProductModel.id == product_id,
                    ProductModel.stock >= quantity
                )
            )
            .values(
                stock=ProductModel.stock - quantity,
                version=ProductModel.version + 1,
                updated_at=func.now()
            )
            .execution_options(synchronize_session=False)
        )
        
        result = await self.session.execute(query)
        return result.rowcount > 0


class OrderRepository:
    """
    Order data access repository.
    
    Order is an aggregate root - it owns OrderItems.
    All access to OrderItems goes through Order.
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, order: OrderModel) -> OrderModel:
        """
        Create new order with items.
        
        DECISION: Add and flush (not commit)
        WHY: Caller controls transaction boundary
        """
        self.session.add(order)
        await self.session.flush()  # Get ID without committing
        await self.session.refresh(order)  # Load relationships
        return order
    
    async def get_by_id(self, order_id: UUID) -> Optional[OrderModel]:
        """
        Get order by ID with items eagerly loaded.
        
        DECISION: Using selectinload for items
        WHY:
          - Separate query for items (not huge JOIN)
          - Items almost always needed
          - Better than N+1 (lazy loading)
        
        ALTERNATIVE: joinedload
          - Single query but larger result set
          - Better for small item counts
        """
        query = (
            select(OrderModel)
            .where(OrderModel.id == order_id)
            .options(
                selectinload(OrderModel.items).selectinload(OrderItemModel.product)
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_id_for_update(
        self, 
        order_id: UUID,
        load_items: bool = True
    ) -> Optional[OrderModel]:
        """
        Get order with row lock for status updates.
        
        DECISION: Lock order, not items
        WHY: Status changes on order, items are immutable after creation
        """
        if load_items:
            query = (
                select(OrderModel)
                .where(OrderModel.id == order_id)
                .options(selectinload(OrderModel.items))
                .with_for_update()
            )
        else:
            query = (
                select(OrderModel)
                .where(OrderModel.id == order_id)
                .with_for_update()
            )
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20,
        status: Optional[OrderStatus] = None
    ) -> List[OrderModel]:
        """
        Get orders for a user with optional status filter.
        
        DECISION: Include items by default
        WHY: UI typically shows order with items
        """
        query = (
            select(OrderModel)
            .where(OrderModel.user_id == user_id)
            .options(selectinload(OrderModel.items))
            .order_by(OrderModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        
        if status:
            query = query.where(OrderModel.status == status)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_status(
        self,
        order_id: UUID,
        new_status: OrderStatus,
        expected_version: int,
        failure_reason: Optional[str] = None,
        paid_at: Optional[datetime] = None
    ) -> bool:
        """
        Update order status with optimistic locking.
        
        DECISION: Version check in WHERE clause
        WHY: Atomic check-and-update, no race window
        
        RETURNS: True if update succeeded
        """
        values = {
            "status": new_status,
            "version": OrderModel.version + 1,
            "updated_at": func.now(),
        }
        
        if failure_reason is not None:
            values["failure_reason"] = failure_reason
        
        if paid_at is not None:
            values["paid_at"] = paid_at
        
        query = (
            update(OrderModel)
            .where(
                and_(
                    OrderModel.id == order_id,
                    OrderModel.version == expected_version
                )
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        
        result = await self.session.execute(query)
        return result.rowcount > 0
    
    async def set_idempotency_key(
        self,
        order_id: UUID,
        idempotency_key: str
    ) -> bool:
        """
        Set idempotency key for payment.
        
        DECISION: Separate method for idempotency
        WHY: Clear intent, single responsibility
        """
        query = (
            update(OrderModel)
            .where(
                and_(
                    OrderModel.id == order_id,
                    OrderModel.idempotency_key.is_(None)  # Only if not set
                )
            )
            .values(idempotency_key=idempotency_key)
            .execution_options(synchronize_session=False)
        )
        
        result = await self.session.execute(query)
        return result.rowcount > 0
    
    async def get_by_idempotency_key(
        self, 
        key: str
    ) -> Optional[OrderModel]:
        """
        Find order by idempotency key.
        
        Used to detect duplicate payment requests.
        """
        query = (
            select(OrderModel)
            .where(OrderModel.idempotency_key == key)
            .options(selectinload(OrderModel.items))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_pending_orders(
        self,
        older_than_minutes: int = 30,
        limit: int = 100
    ) -> List[OrderModel]:
        """
        Get stale pending orders for cleanup/retry.
        
        DECISION: Separate method for batch operations
        WHY: Clear intent, can optimize separately
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        
        query = (
            select(OrderModel)
            .where(
                and_(
                    OrderModel.status == OrderStatus.PENDING,
                    OrderModel.created_at < cutoff
                )
            )
            .order_by(OrderModel.created_at)
            .limit(limit)
        )
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_total_price(
        self,
        order_id: UUID,
        total_price: int
    ) -> bool:
        """Update order total price."""
        query = (
            update(OrderModel)
            .where(OrderModel.id == order_id)
            .values(
                total_price=total_price,
                updated_at=func.now()
            )
            .execution_options(synchronize_session=False)
        )
        
        result = await self.session.execute(query)
        return result.rowcount > 0


# ============================================================================
# REPOSITORY FACTORY
# ============================================================================

class RepositoryFactory:
    """
    Factory for creating repositories.
    
    DECISION: Factory pattern for repository creation
    WHY:
      - Centralized creation logic
      - Easy to add cross-cutting concerns (logging, caching)
      - Simplifies dependency injection
    
    ALTERNATIVE: Create repositories directly
      - Simpler but less flexible
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._product_repo: Optional[ProductRepository] = None
        self._order_repo: Optional[OrderRepository] = None
    

    @property
    def products(self) -> ProductRepository:
        """Get or create product repository."""
        if self._product_repo is None:
            self._product_repo = ProductRepository(self.session)
        return self._product_repo


    @property
    def orders(self) -> OrderRepository:
        """Get or create order repository."""
        if self._order_repo is None:
            self._order_repo = OrderRepository(self.session)
        return self._order_repo


# ============================================================================
# FASTAPI DEPENDENCY
# ============================================================================

from fastapi import Depends
from app.infrastructure.database.session import get_db_session

async def get_repositories(
    session: AsyncSession = Depends(get_db_session)
) -> RepositoryFactory:
    """
    FastAPI dependency for repositories.
    
    USAGE:
        @app.get("/products")
        async def list_products(repos: RepositoryFactory = Depends(get_repositories)):
            return await repos.products.get_all()
    """
    return RepositoryFactory(session)
