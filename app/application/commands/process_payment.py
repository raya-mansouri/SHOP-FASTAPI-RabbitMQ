"""
Process Payment Command.

RESPONSIBILITY: Handle payment processing (write operation)

This is the CRITICAL command that:
1. Validates order state
2. Checks idempotency
3. Locks products (prevents race conditions)
4. Deducts stock
5. Updates order status
6. Invalidates caches

CALLED BY: Worker (async) or API (sync for simple cases)
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.commands.base import Command
from app.api.schemas import PaymentResponse
from app.domain.exceptions import (
    InsufficientStockError,
    OptimisticLockError,
    OrderNotFoundError,
    OrderNotPendingError,
)
from app.infrastructure.database.models import OrderStatus
from app.infrastructure.database.repositories import (
    OrderRepository,
    ProductRepository,
)
from app.infrastructure.cache import CacheService, CacheKeys


class InitiatePaymentCommand(Command[PaymentResponse]):
    """
    Command to initiate payment (API endpoint calls this).
    
    This does NOT process payment - it:
    1. Validates order can be paid
    2. Checks idempotency
    3. Updates status to PROCESSING
    4. Queues for async processing
    """
    
    def __init__(
        self,
        order_id: UUID,
        session: AsyncSession,
        cache: CacheService,
        idempotency_key: Optional[str] = None
    ):
        self.order_id = order_id
        self.session = session
        self.cache = cache
        self.idempotency_key = idempotency_key
        self.order_repo = OrderRepository(session)
    
    async def execute(self) -> PaymentResponse:
        """
        Initiate payment process.
        
        IDEMPOTENCY HANDLING:
        - Check if idempotency key was already used
        - If yes, return previous result (no duplicate charge)
        - If no, proceed with new payment
        """
        # 1. Check idempotency (fast path for duplicates)
        if self.idempotency_key:
            existing = await self.cache.check_idempotency(self.idempotency_key)
            if existing:
                return PaymentResponse(
                    order_id=UUID(existing["order_id"]),
                    status=existing["status"],
                    message="Payment already processed (idempotent)"
                )
        
        # 2. Acquire distributed lock for this order
        lock_key = CacheKeys.lock_payment(str(self.order_id))
        lock_acquired = await self.cache.acquire_lock(lock_key, ttl=30)
        
        if not lock_acquired:
            return PaymentResponse(
                order_id=self.order_id,
                status="PROCESSING",
                message="Payment already in progress"
            )
        
        try:
            # 3. Get order with database lock
            order = await self.order_repo.get_by_id_for_update(
                self.order_id, 
                load_items=False
            )
            
            if order is None:
                raise OrderNotFoundError(str(self.order_id))
            
            # 4. Validate order status
            if order.status == OrderStatus.PAID:
                result = PaymentResponse(
                    order_id=self.order_id,
                    status=OrderStatus.PAID.value,
                    message="Order already paid"
                )
                # Store for idempotency
                if self.idempotency_key:
                    await self.cache.set_idempotency(
                        self.idempotency_key,
                        {"order_id": str(self.order_id), "status": "PAID"}
                    )
                return result
            
            if order.status != OrderStatus.PENDING:
                raise OrderNotPendingError(str(self.order_id), order.status.value)
            
            # 5. Set idempotency key on order
            if self.idempotency_key:
                await self.order_repo.set_idempotency_key(
                    order_id=self.order_id,
                    idempotency_key=self.idempotency_key
                )
            
            # 6. Update status to PROCESSING
            await self.order_repo.update_status(
                order_id=self.order_id,
                new_status=OrderStatus.PROCESSING,
                expected_version=order.version
            )
            
            # 7. TODO: Publish to RabbitMQ for async processing
            # await self.message_publisher.publish_payment(self.order_id)
            
            return PaymentResponse(
                order_id=self.order_id,
                status=OrderStatus.PROCESSING.value,
                message="Payment is being processed"
            )
            
        finally:
            # Always release lock
            await self.cache.release_lock(lock_key)


class ProcessPaymentCommand(Command[bool]):
    """
    Command to actually process payment (Worker calls this).
    
    CRITICAL OPERATIONS:
    1. Lock products (FOR UPDATE)
    2. Validate stock
    3. Deduct stock atomically
    4. Update order to PAID
    
    ALL IN ONE TRANSACTION!
    """
    
    def __init__(
        self,
        order_id: UUID,
        session: AsyncSession,
        cache: CacheService
    ):
        self.order_id = order_id
        self.session = session
        self.cache = cache
        self.order_repo = OrderRepository(session)
        self.product_repo = ProductRepository(session)
    
    async def execute(self) -> bool:
        """
        Process payment - deduct stock and mark as paid.
        
        RETURNS: True if successful
        RAISES: Various exceptions on failure
        """
        # 1. Get order with lock and items
        order = await self.order_repo.get_by_id_for_update(
            self.order_id, 
            load_items=True
        )
        
        if order is None:
            raise OrderNotFoundError(str(self.order_id))
        
        # 2. Check status (idempotent - already paid is success)
        if order.status == OrderStatus.PAID:
            return True
        
        if order.status != OrderStatus.PROCESSING:
            raise OrderNotPendingError(str(self.order_id), order.status.value)
        
        # 3. Get product IDs
        product_ids = [item.product_id for item in order.items]
        
        # 4. Lock products in consistent order (PREVENTS DEADLOCKS!)
        products = await self.product_repo.get_by_ids_for_update(product_ids)
        product_map = {p.id: p for p in products}
        
        # 5. Validate products exist
        for item in order.items:
            if item.product_id not in product_map:
                await self._fail_order(
                    order, 
                    f"Product {item.product_id} no longer exists"
                )
                return False
        
        # 6. Validate stock
        insufficient = []
        for item in order.items:
            product = product_map[item.product_id]
            if product.stock < item.quantity:
                insufficient.append({
                    "product_id": product.id,
                    "name": product.name,
                    "requested": item.quantity,
                    "available": product.stock
                })
        
        if insufficient:
            await self._fail_order(
                order,
                f"Insufficient stock: {insufficient}"
            )
            raise InsufficientStockError(
                product_id=insufficient[0]["product_id"],
                product_name=insufficient[0]["name"],
                requested=insufficient[0]["requested"],
                available=insufficient[0]["available"]
            )
        
        # 7. Deduct stock for all items
        for item in order.items:
            product = product_map[item.product_id]
            success = await self.product_repo.update_stock(
                product_id=product.id,
                quantity_delta=-item.quantity,
                expected_version=product.version
            )
            
            if not success:
                raise OptimisticLockError("Product", product.id)
        
        # 8. Update order to PAID
        success = await self.order_repo.update_status(
            order_id=self.order_id,
            new_status=OrderStatus.PAID,
            expected_version=order.version,
            paid_at=datetime.now(timezone.utc)
        )
        
        if not success:
            raise OptimisticLockError("Order", str(self.order_id))
        
        # 9. Invalidate caches
        await self._invalidate_caches(order, product_ids)
        
        return True
    
    async def _fail_order(self, order, reason: str) -> None:
        """Mark order as failed."""
        await self.order_repo.update_status(
            order_id=self.order_id,
            new_status=OrderStatus.FAILED,
            expected_version=order.version,
            failure_reason=reason
        )
        
        # Invalidate order cache
        await self.cache.delete(CacheKeys.order(str(self.order_id)))
        await self.cache.delete_pattern(
            CacheKeys.user_orders_pattern(order.user_id)
        )
    
    async def _invalidate_caches(self, order, product_ids: list) -> None:
        """Invalidate all affected caches after successful payment."""
        # Order caches
        await self.cache.delete(CacheKeys.order(str(self.order_id)))
        await self.cache.delete_pattern(
            CacheKeys.user_orders_pattern(order.user_id)
        )
        
        # Product caches (stock changed)
        for pid in product_ids:
            await self.cache.delete(CacheKeys.product(pid))
            await self.cache.delete(CacheKeys.product_stock(pid))
        
        # Product list cache (stock changed)
        await self.cache.delete_pattern(CacheKeys.all_products_pattern())