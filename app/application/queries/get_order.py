"""
Get Order Queries.

READ PATH: Redis -> PostgreSQL

CACHING STRATEGY:
- Order: Cached for 1 minute (status may change)
- User orders: Cached for 1 minute
- Cache invalidated on order status change
"""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.queries.base import Query
from app.api.schemas import OrderResponse, OrderItemResponse
from app.infrastructure.database.repositories import OrderRepository
from app.infrastructure.database.models import OrderModel
from app.infrastructure.cache import CacheService, CacheKeys


class GetOrderByIdQuery(Query[Optional[OrderResponse]]):
    """
    Query to get order by ID with all items.
    
    CACHING: Short TTL (1 min) because order status changes
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
        self.repository = OrderRepository(session)
    
    async def execute(self) -> Optional[OrderResponse]:
        """Execute query with caching."""
        cache_key = CacheKeys.order(str(self.order_id))
        
        # 1. Try cache
        cached = await self.cache.get_model(cache_key, OrderResponse)
        if cached is not None:
            return cached
        
        # 2. Cache miss - query database
        order = await self.repository.get_by_id(self.order_id)
        
        if order is None:
            return None
        
        # 3. Convert to response
        result = self._to_response(order)
        
        # 4. Cache with short TTL (order status may change)
        await self.cache.set_model(
            cache_key, 
            result, 
            ttl=CacheKeys.TTL_SHORT
        )
        
        return result
    
    def _to_response(self, order: OrderModel) -> OrderResponse:
        """Convert ORM model to response."""
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


class GetUserOrdersQuery(Query[List[OrderResponse]]):
    """
    Query to get all orders for a user.
    """
    
    def __init__(
        self,
        user_id: int,
        session: AsyncSession,
        cache: CacheService,
        skip: int = 0,
        limit: int = 20
    ):
        self.user_id = user_id
        self.session = session
        self.cache = cache
        self.skip = skip
        self.limit = limit
        self.repository = OrderRepository(session)
    
    async def execute(self) -> List[OrderResponse]:
        """Execute query with caching."""
        cache_key = CacheKeys.user_orders(self.user_id, self.skip, self.limit)
        
        # 1. Try cache
        cached = await self.cache.get_list(cache_key, OrderResponse)
        if cached is not None:
            return cached
        
        # 2. Cache miss - query database
        orders = await self.repository.get_by_user(
            user_id=self.user_id,
            skip=self.skip,
            limit=self.limit
        )
        
        # 3. Convert to responses
        results = [self._to_response(order) for order in orders]
        
        # 4. Cache
        await self.cache.set_list(
            cache_key,
            results,
            ttl=CacheKeys.TTL_SHORT
        )
        
        return results
    
    def _to_response(self, order: OrderModel) -> OrderResponse:
        """Convert ORM model to response."""
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