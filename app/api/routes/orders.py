# app/api/routes/orders.py
"""
Order API Routes.

ENDPOINTS:
- POST /orders - Create a new order
- GET /orders/{id} - Get order details
- POST /orders/{id}/pay - Initiate payment
"""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_db_session
from app.infrastructure.cache import get_cache_service, CacheService
from app.infrastructure.messaging import get_rabbitmq_publisher, RabbitMQPublisher
from app.application.commands import CreateOrderCommand, InitiatePaymentCommand
from app.application.queries import GetOrderByIdQuery
from app.api.schemas import (
    OrderCreate,
    OrderResponse,
    OrderCreateResponse,
    PaymentRequest,
    PaymentResponse,
)
from app.domain.exceptions import (
    OrderNotFoundError,
    OrderNotPendingError,
    OrderAlreadyPaidError,
    InsufficientStockError,
    ProductNotFoundError,
)

router = APIRouter()


# Type aliases for cleaner dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
Cache = Annotated[CacheService, Depends(get_cache_service)]
MQPublisher = Annotated[RabbitMQPublisher, Depends(get_rabbitmq_publisher)]


@router.post("", response_model=OrderCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    db: DbSession,
    cache: Cache,
):
    """
    Create a new order.
    
    - **user_id**: ID of the user placing the order
    - **items**: List of products and quantities
    
    Returns the created order ID and status.
    Stock is NOT reserved at this point - it will be checked during payment.
    """
    try:
        command = CreateOrderCommand(
            data=order_data,
            session=db,
            cache=cache,
        )
        return await command.execute()
        
    except ProductNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )
    except InsufficientStockError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: DbSession,
    cache: Cache,
):
    """
    Get order details by ID.
    
    - **order_id**: UUID of the order to retrieve
    
    Returns complete order details including items.
    """
    query = GetOrderByIdQuery(
        order_id=order_id,
        session=db,
        cache=cache,
    )
    result = await query.execute()
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with id {order_id} not found",
        )
    
    return result


@router.post("/{order_id}/pay", response_model=PaymentResponse, status_code=status.HTTP_202_ACCEPTED)
async def initiate_payment(
    order_id: UUID,
    payment_data: PaymentRequest,
    db: DbSession,
    cache: Cache,
    publisher: MQPublisher,
):
    """
    Initiate payment for an order.
    
    - **order_id**: UUID of the order to pay
    - **idempotency_key**: Optional key to prevent duplicate payments
    
    This endpoint:
    1. Validates the order can be paid
    2. Updates order status to PROCESSING
    3. Publishes message to RabbitMQ for async processing
    
    Returns immediately with PROCESSING status.
    Actual payment processing happens asynchronously.
    """
    try:
        # Execute payment initiation command
        command = InitiatePaymentCommand(
            order_id=order_id,
            session=db,
            cache=cache,
            idempotency_key=payment_data.idempotency_key,
        )
        result = await command.execute()
        
        # Publish to RabbitMQ for async processing
        if result.status == "PROCESSING":
            await publisher.publish_payment(
                order_id=order_id,
                idempotency_key=payment_data.idempotency_key,
            )
        
        return result
        
    except OrderNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.to_dict(),
        )
    except OrderAlreadyPaidError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )
    except OrderNotPendingError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.to_dict(),
        )
