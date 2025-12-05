"""
Create Order Command.

RESPONSIBILITY: Handle order creation (write operation)

FLOW:
1. Validate input data
2. Verify products exist
3. Check stock availability (soft check)
4. Calculate total price
5. Create order in database
6. Invalidate relevant caches
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.commands.base import Command
from app.api.schemas import OrderCreate, OrderCreateResponse
from app.domain.exceptions import (
    EmptyOrderError,
    InsufficientStockError,
    InvalidQuantityError,
    ProductNotFoundError,
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
from app.infrastructure.cache import CacheService, CacheKeys


class CreateOrderCommand(Command[OrderCreateResponse]):
    """
    Command to create a new order.
    
    DEPENDENCIES:
    - session: Database session (write path)
    - cache: Cache service (for invalidation)
    
    DECISION: Stock not reserved on creation
    WHY:
      - Avoids inventory lockup from abandoned carts
      - Stock deducted at payment time
      - Simpler concurrency model
    """
    
    def __init__(
        self,
        data: OrderCreate,
        session: AsyncSession,
        cache: Optional[CacheService] = None
    ):
        self.data = data
        self.session = session
        self.cache = cache
        self.order_repo = OrderRepository(session)
        self.product_repo = ProductRepository(session)
    
    async def execute(self) -> OrderCreateResponse:
        """
        Execute order creation.
        
        STEPS:
        1. Validate input
        2. Fetch products
        3. Validate stock
        4. Create order
        5. Invalidate cache
        """
        # 1. Validate items not empty
        if not self.data.items:
            raise EmptyOrderError()
        
        # 2. Validate quantities
        for item in self.data.items:
            if item.quantity <= 0:
                raise InvalidQuantityError(item.quantity)
        
        # 3. Fetch products from database (write source of truth)
        product_ids = [item.product_id for item in self.data.items]
        products = await self.product_repo.get_by_ids(product_ids)
        
        # 4. Validate all products exist
        product_map = {p.id: p for p in products}
        for item in self.data.items:
            if item.product_id not in product_map:
                raise ProductNotFoundError(item.product_id)
        
        # 5. Soft check stock (informational - real check at payment)
        for item in self.data.items:
            product = product_map[item.product_id]
            if product.stock < item.quantity:
                raise InsufficientStockError(
                    product_id=product.id,
                    product_name=product.name,
                    requested=item.quantity,
                    available=product.stock
                )
        
        # 6. Calculate total and create order items
        total_price = 0
        order_items = []
        
        for item in self.data.items:
            product = product_map[item.product_id]
            unit_price = product.price
            subtotal = unit_price * item.quantity
            total_price += subtotal
            
            order_items.append(OrderItemModel(
                product_id=item.product_id,
                quantity=item.quantity,
                unit_price=unit_price,
            ))
        
        # 7. Create order
        order = OrderModel(
            user_id=self.data.user_id,
            status=OrderStatus.PENDING,
            total_price=total_price,
        )
        order.items = order_items
        
        # 8. Save to database
        created_order = await self.order_repo.create(order)
        
        # 9. Invalidate user orders cache
        if self.cache:
            await self.cache.delete_pattern(
                CacheKeys.user_orders_pattern(self.data.user_id)
            )
        
        return OrderCreateResponse(
            id=created_order.id,
            status=created_order.status.value,
            message="Order created successfully. Proceed to payment."
        )