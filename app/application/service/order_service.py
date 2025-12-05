"""
Order Service - Application Layer.

RESPONSIBILITY: Orchestrates order-related use cases
  - Create order
  - Get order
  - Initiate payment
  - Process payment (called by worker)

This is the CORE of your business logic and where
most edge cases are handled.

DECISION: All business rules enforced here
WHY:
  - Single source of truth for order logic
  - Easy to test
  - API routes stay thin
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    EmptyOrderError,
    InsufficientStockError,
    InvalidQuantityError,
    OrderAlreadyPaidError,
    OrderNotFoundError,
    OrderNotPendingError,
    ProductNotFoundError,
    OptimisticLockError,
    DuplicatePaymentError,
)
from app.infrastructure.database.models import (
    OrderItemModel,
    OrderModel,
    OrderStatus,
)
from app.infrastructure.database.repositories import (
    OrderRepository,
    ProductRepository,
)
from app.api.schemas import (
    OrderCreate,
    OrderResponse,
    OrderItemResponse,
    OrderCreateResponse,
    PaymentResponse,
)


class OrderService:
    """
    Order service handles all order-related operations.
    
    CRITICAL EDGE CASES HANDLED:
    1. Product doesn't exist
    2. Insufficient stock
    3. Concurrent stock updates (race condition)
    4. Order not found
    5. Order already paid
    6. Duplicate payment (idempotency)
    7. Order status transitions
    """
    
    def __init__(
        self,
        order_repository: OrderRepository,
        product_repository: ProductRepository,
        session: AsyncSession
    ):
        self.order_repo = order_repository
        self.product_repo = product_repository
        self.session = session
    
    # ========================================================================
    # CREATE ORDER
    # ========================================================================
    
    async def create_order(self, data: OrderCreate) -> OrderCreateResponse:
        """
        Create a new order.
        
        FLOW:
        1. Validate input
        2. Fetch and validate products exist
        3. Check stock availability (soft check)
        4. Calculate total price
        5. Create order with items
        
        NOTE: Stock is NOT deducted here!
        Stock is deducted during payment processing to avoid
        holding inventory for unpaid orders.
        
        DECISION: Don't reserve stock on order creation
        WHY:
          - Avoids inventory lockup from abandoned carts
          - Simpler concurrency model
          - Payment is where money matters
        
        ALTERNATIVE: Reserve stock on creation, release if unpaid
          - More complex
          - Need background job to release expired reservations
        """
        # 1. Validate items not empty
        if not data.items:
            raise EmptyOrderError()
        
        # 2. Validate quantities
        for item in data.items:
            if item.quantity <= 0:
                raise InvalidQuantityError(item.quantity)
        
        # 3. Fetch products
        product_ids = [item.product_id for item in data.items]
        products = await self.product_repo.get_by_ids(product_ids)
        
        # 4. Validate all products exist
        product_map = {p.id: p for p in products}
        for item in data.items:
            if item.product_id not in product_map:
                raise ProductNotFoundError(item.product_id)
        
        # 5. Soft check stock (informational - not guaranteed)
        # Real check happens at payment time
        for item in data.items:
            product = product_map[item.product_id]
            if product.stock < item.quantity:
                raise InsufficientStockError(
                    product_id=product.id,
                    product_name=product.name,
                    requested=item.quantity,
                    available=product.stock
                )
        
        # 6. Calculate total price (using current prices)
        total_price = 0
        order_items = []
        
        for item in data.items:
            product = product_map[item.product_id]
            unit_price = product.price
            subtotal = unit_price * item.quantity
            total_price += subtotal
            
            order_items.append(OrderItemModel(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=unit_price,  # Capture price at order time
            ))
        
        # 7. Create order
        order = OrderModel(
            user_id=data.user_id,
            status=OrderStatus.PENDING,
            total_price=total_price,
        )
        order.items = order_items
        
        # 8. Save to database
        created_order = await self.order_repo.create(order)
        
        return OrderCreateResponse(
            id=created_order.id,
            status=created_order.status.value,
            message="Order created successfully. Proceed to payment."
        )
    
    # ========================================================================
    # GET ORDER
    # ========================================================================
    
    async def get_order(self, order_id: UUID) -> OrderResponse:
        """
        Get order by ID with all items.
        
        RAISES: OrderNotFoundError if not exists
        """
        order = await self.order_repo.get_by_id(order_id)
        
        if order is None:
            raise OrderNotFoundError(str(order_id))
        
        return self._order_to_response(order)
    
    async def get_user_orders(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 20
    ) -> List[OrderResponse]:
        """Get all orders for a user."""
        orders = await self.order_repo.get_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit
        )
        
        return [self._order_to_response(order) for order in orders]
    
    # ========================================================================
    # PAYMENT INITIATION (API calls this)
    # ========================================================================
    
    async def initiate_payment(
        self,
        order_id: UUID,
        idempotency_key: Optional[str] = None
    ) -> PaymentResponse:
        """
        Initiate payment for an order.
        
        This method:
        1. Validates order can be paid
        2. Checks for duplicate payment (idempotency)
        3. Queues order for async processing
        
        ACTUAL payment processing happens in the WORKER.
        
        DECISION: Payment is async via message queue
        WHY:
          - Non-blocking API response
          - Retry capability
          - Scalable with multiple workers
        
        EDGE CASES:
        - Order not found -> OrderNotFoundError
        - Order not pending -> OrderNotPendingError
        - Duplicate payment key -> DuplicatePaymentError (return existing)
        """
        # 1. Check idempotency key first (fast path for duplicates)
        if idempotency_key:
            existing = await self.order_repo.get_by_idempotency_key(idempotency_key)
            if existing:
                # Return success - idempotent behavior
                return PaymentResponse(
                    order_id=existing.id,
                    status=existing.status.value,
                    message="Payment already processed (idempotent)"
                )
        
        # 2. Get order with lock to prevent concurrent payment initiation
        order = await self.order_repo.get_by_id_for_update(order_id, load_items=False)
        
        if order is None:
            raise OrderNotFoundError(str(order_id))
        
        # 3. Validate order status
        if order.status == OrderStatus.PAID:
            raise OrderAlreadyPaidError(str(order_id))
        
        if order.status != OrderStatus.PENDING:
            raise OrderNotPendingError(str(order_id), order.status.value)
        
        # 4. Set idempotency key if provided
        if idempotency_key:
            success = await self.order_repo.set_idempotency_key(
                order_id=order_id,
                idempotency_key=idempotency_key
            )
            if not success:
                # Key was set by concurrent request - check again
                existing = await self.order_repo.get_by_idempotency_key(idempotency_key)
                if existing and existing.id != order_id:
                    raise DuplicatePaymentError(idempotency_key, str(existing.id))
        
        # 5. Update status to PROCESSING
        await self.order_repo.update_status(
            order_id=order_id,
            new_status=OrderStatus.PROCESSING,
            expected_version=order.version
        )
        
        # 6. Publish to message queue (will implement later)
        # await self.message_publisher.publish_payment(order_id)
        
        # For now, return that payment is being processed
        return PaymentResponse(
            order_id=order_id,
            status=OrderStatus.PROCESSING.value,
            message="Payment is being processed"
        )
    
    # ========================================================================
    # PAYMENT PROCESSING (Worker calls this)
    # ========================================================================
    
    async def process_payment(self, order_id: UUID) -> bool:
        """
        Process payment for an order.
        
        THIS IS CALLED BY THE WORKER, NOT THE API.
        
        FLOW:
        1. Get order with lock
        2. Validate status is PROCESSING
        3. Get products with locks (FOR UPDATE)
        4. Validate stock availability
        5. Deduct stock atomically
        6. Update order status to PAID
        
        CRITICAL: All operations in single transaction!
        
        CONCURRENCY HANDLING:
        - SELECT FOR UPDATE on products (pessimistic lock)
        - Optimistic locking as backup (version field)
        - Ordered locking to prevent deadlocks
        
        RETURNS: True if successful, raises exception on failure
        """
        # 1. Get order with lock
        order = await self.order_repo.get_by_id_for_update(order_id, load_items=True)
        
        if order is None:
            raise OrderNotFoundError(str(order_id))
        
        # 2. Validate status
        if order.status == OrderStatus.PAID:
            # Already paid - idempotent success
            return True
        
        if order.status != OrderStatus.PROCESSING:
            raise OrderNotPendingError(str(order_id), order.status.value)
        
        # 3. Get product IDs from order items
        product_ids = [item.product_id for item in order.items]
        
        # 4. Lock products in consistent order (PREVENTS DEADLOCKS!)
        products = await self.product_repo.get_by_ids_for_update(product_ids)
        product_map = {p.id: p for p in products}
        
        # 5. Validate all products still exist
        for item in order.items:
            if item.product_id not in product_map:
                # Product was deleted - fail the order
                await self._fail_order(
                    order_id=order_id,
                    version=order.version,
                    reason=f"Product {item.product_id} no longer exists"
                )
                return False
        
        # 6. Validate stock availability
        insufficient_stock = []
        for item in order.items:
            product = product_map[item.product_id]
            if product.stock < item.quantity:
                insufficient_stock.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "requested": item.quantity,
                    "available": product.stock
                })
        
        if insufficient_stock:
            # Not enough stock - fail the order
            reason = f"Insufficient stock: {insufficient_stock}"
            await self._fail_order(
                order_id=order_id,
                version=order.version,
                reason=reason
            )
            raise InsufficientStockError(
                product_id=insufficient_stock[0]["product_id"],
                product_name=insufficient_stock[0]["product_name"],
                requested=insufficient_stock[0]["requested"],
                available=insufficient_stock[0]["available"]
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
                # Concurrent modification - this shouldn't happen with FOR UPDATE
                # but we have it as defense in depth
                raise OptimisticLockError("Product", product.id)
        
        # 8. Update order status to PAID
        success = await self.order_repo.update_status(
            order_id=order_id,
            new_status=OrderStatus.PAID,
            expected_version=order.version,
            paid_at=datetime.now(timezone.utc)
        )
        
        if not success:
            raise OptimisticLockError("Order", str(order_id))
        
        return True
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    async def _fail_order(
        self,
        order_id: UUID,
        version: int,
        reason: str
    ) -> None:
        """Mark order as failed with reason."""
        await self.order_repo.update_status(
            order_id=order_id,
            new_status=OrderStatus.FAILED,
            expected_version=version,
            failure_reason=reason
        )
    
    def _order_to_response(self, order: OrderModel) -> OrderResponse:
        """Convert ORM model to response schema."""
        items = [
            OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name if item.product else None,
                quantity=item.quantity,
                unit_price=item.unit_price,
                subtotal=item.unit_price * item.quantity
            )
            for item in order.items
        ]
        
        return OrderResponse(
            id=order.id,
            user_id=order.user_id,
            status=order.status.value,
            total_price=order.total_price,
            items=items,
            created_at=order.created_at,
            updated_at=order.updated_at,
            paid_at=order.paid_at,
            failure_reason=order.failure_reason
        )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_order_service(session: AsyncSession) -> OrderService:
    """Factory function to create OrderService."""
    order_repo = OrderRepository(session)
    product_repo = ProductRepository(session)
    return OrderService(order_repo, product_repo, session)