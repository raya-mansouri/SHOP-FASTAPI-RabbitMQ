"""
Background worker for processing order payments.
This is THE MOST CRITICAL component for handling race conditions.

Key responsibilities:
1. Consume messages from RabbitMQ
2. Validate stock availability
3. Deduct stock atomically (SELECT FOR UPDATE)
4. Update order status
5. Handle failures gracefully
"""
import asyncio
import json
import logging
import signal
from datetime import datetime, timezone
from typing import Dict

from aio_pika import connect_robust, IncomingMessage, ExchangeType
from aio_pika.abc import AbstractConnection, AbstractChannel
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.infrastructure.database.session import sessionmanager
from app.infrastructure.database.repositories import (
    OrderRepository,
    ProductRepository
)
from app.infrastructure.cache.cache_service import CacheService
from app.infrastructure.cache.redis_client import RedisManager
from app.infrastructure.cache.keys import CacheKeys
from app.infrastructure.database.models import OrderStatus
from app.domain.exceptions import (
    EntityNotFoundError,
    InsufficientStockError,
    ConcurrencyError
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrderProcessor:
    """
    Worker for processing order payments.
    
    Edge cases handled:
    1. Order not found
    2. Insufficient stock for any item
    3. Concurrent stock updates (SELECT FOR UPDATE)
    4. Database deadlocks (retry with backoff)
    5. Message processing failures (requeue)
    6. Worker crashes (RabbitMQ redelivery)
    7. Duplicate message processing (idempotency in DB)
    """
    
    def __init__(self):
        self.connection: AbstractConnection | None = None
        self.channel: AbstractChannel | None = None
        self.cache_service: CacheService | None = None
        self.redis_manager: RedisManager | None = None
        self.running = False
    
    async def start(self):
        """Start the worker and begin consuming messages."""
        logger.info("Starting order processor worker")
        
        # Database is already initialized via sessionmanager
        # No explicit init needed
        
        # Initialize cache
        self.redis_manager = RedisManager()
        await self.redis_manager.connect()
        redis_client = self.redis_manager.get_client()
        self.cache_service = CacheService(redis_client)
        
        # Connect to RabbitMQ
        await self._connect_rabbitmq()
        
        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self.stop())
            )
        
        self.running = True
        logger.info("Order processor worker started successfully")
        
        # Keep running
        try:
            await asyncio.Future()  # Run forever
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """Gracefully stop the worker."""
        logger.info("Stopping order processor worker...")
        self.running = False
        
        if self.channel:
            await self.channel.close()
        
        if self.connection:
            await self.connection.close()

        if self.redis_manager:
            await self.redis_manager.disconnect()

        await sessionmanager.close()
        
        logger.info("Order processor worker stopped")
    
    async def _connect_rabbitmq(self):
        """Connect to RabbitMQ and start consuming."""
        self.connection = await connect_robust(
            settings.get_rabbitmq_url(),
            timeout=30
        )
        
        self.channel = await self.connection.channel()
        await self.channel.set_qos(
            prefetch_count=settings.rabbitmq_prefetch_count
        )
        
        # Declare exchange
        exchange = await self.channel.declare_exchange(
            settings.rabbitmq_exchange_name,
            ExchangeType.DIRECT,
            durable=True
        )
        
        # Declare queue
        queue = await self.channel.declare_queue(
            settings.rabbitmq_queue_name,
            durable=True
        )
        
        # Bind queue
        await queue.bind(exchange, routing_key=settings.rabbitmq_routing_key)
        
        # Start consuming
        await queue.consume(self._process_message)
        
        logger.info(
            "RabbitMQ consumer started",
            extra={
                "queue": settings.rabbitmq_queue_name,
                "prefetch": settings.rabbitmq_prefetch_count
            }
        )
    
    async def _process_message(self, message: IncomingMessage):
        """
        Process incoming message.
        
        Critical: This method MUST be idempotent!
        Messages may be redelivered if worker crashes.
        """
        async with message.process(ignore_processed=True):
            try:
                # Parse message
                body = json.loads(message.body.decode())
                order_id = body.get("order_id")
                user_id = body.get("user_id")
                idempotency_key = body.get("idempotency_key")
                
                # Check redelivery count to prevent infinite loops
                redelivery_count = message.headers.get("x-delivery-count", 0) if message.headers else 0
                max_redeliveries = 10  # Prevent infinite requeue loops
                
                logger.info(
                    "Processing order payment",
                    extra={
                        "order_id": order_id,
                        "user_id": user_id,
                        "delivery_tag": message.delivery_tag,
                        "redelivered": message.redelivered,
                        "redelivery_count": redelivery_count
                    }
                )
                
                # If redelivered too many times, reject without requeue
                if redelivery_count >= max_redeliveries:
                    logger.error(
                        f"Order {order_id} exceeded max redeliveries ({max_redeliveries}), rejecting",
                        extra={"order_id": order_id, "redelivery_count": redelivery_count}
                    )
                    await message.reject(requeue=False)
                    return
                
                # Process with retries
                success = await self._process_order_payment(
                    order_id,
                    idempotency_key
                )
                
                if success:
                    # Acknowledge message
                    await message.ack()
                    logger.info(
                        "Order payment processed successfully",
                        extra={"order_id": order_id}
                    )
                else:
                    # Reject and requeue (will retry)
                    await message.reject(requeue=True)
                    logger.warning(
                        "Order payment processing failed, requeuing",
                        extra={"order_id": order_id, "redelivery_count": redelivery_count}
                    )
            
            except json.JSONDecodeError as e:
                # Invalid message format - don't requeue
                logger.error(f"Invalid message format: {e}", exc_info=True)
                await message.reject(requeue=False)
            
            except Exception as e:
                # Unexpected error - log and requeue
                logger.error(
                    f"Unexpected error processing message: {e}",
                    exc_info=True
                )
                await message.reject(requeue=True)
    
    async def _process_order_payment(
        self,
        order_id: int,
        idempotency_key: str | None = None
    ) -> bool:
        """
        Process order payment with stock deduction.
        
        This is THE CRITICAL SECTION with race condition handling!
        
        Steps:
        1. Start transaction
        2. Fetch order (with lock if needed)
        3. For each item:
           a. SELECT FOR UPDATE on product (row lock)
           b. Validate stock
           c. Deduct stock
        4. Update order status to PAID
        5. Commit transaction
        
        Returns:
            True if successful, False otherwise
        """
        max_retries = settings.rabbitmq_max_retries
        
        for attempt in range(max_retries):
            try:
                async with sessionmanager.transaction() as session:
                    order_repo = OrderRepository(session)
                    product_repo = ProductRepository(session)
                    
                    # Step 1: Fetch order
                    order = await order_repo.get_by_id(order_id)
                    
                    if not order:
                        logger.error(f"Order {order_id} not found")
                        return False
                    
                    # Edge Case: Order already paid (idempotent)
                    if order.status == OrderStatus.PAID:
                        logger.info(
                            f"Order {order_id} already paid, skipping"
                        )
                        return True
                    
                    # Edge Case: Order in wrong state
                    if order.status not in [OrderStatus.PENDING, OrderStatus.PROCESSING, OrderStatus.FAILED]:
                        logger.error(
                            f"Order {order_id} in invalid state: {order.status}"
                        )
                        return False
                    
                    # Step 2: Validate and deduct stock for each item
                    # This is THE CRITICAL SECTION for race conditions
                    try:
                        for item in order.items:
                            # CRITICAL: SELECT FOR UPDATE locks the row
                            product = await product_repo.deduct_stock(
                                product_id=item.product_id,
                                quantity=item.quantity
                            )
                            
                            logger.debug(
                                "Stock deducted",
                                extra={
                                    "order_id": order_id,
                                    "product_id": item.product_id,
                                    "quantity": item.quantity,
                                    "remaining_stock": product.stock
                                }
                            )
                    
                    except InsufficientStockError as e:
                        # Not enough stock - mark order as FAILED
                        logger.warning(
                            f"Insufficient stock for order {order_id}: {e}"
                        )
                        
                        await order_repo.update_status(
                            order_id=order_id,
                            new_status=OrderStatus.FAILED,
                            expected_version=order.version,
                            failure_reason=str(e)
                        )
                        
                        # Clear cache
                        if self.cache_service:
                            await self.cache_service.delete(
                                CacheKeys.order(str(order_id))
                            )
                        
                        return True  # Successfully processed (marked as failed)
                    
                    except EntityNotFoundError as e:
                        logger.error(f"Product not found: {e}")
                        await order_repo.update_status(
                            order_id=order_id,
                            new_status=OrderStatus.FAILED,
                            expected_version=order.version,
                            failure_reason=str(e)
                        )
                        return True
                    
                    # Step 3: Mark order as PAID
                    await order_repo.update_status(
                        order_id=order_id,
                        new_status=OrderStatus.PAID,
                        expected_version=order.version,
                        paid_at=datetime.now(timezone.utc)
                    )
                    
                    # Clear caches
                    if self.cache_service:
                        await self.cache_service.delete(CacheKeys.order(str(order_id)))

                        # Invalidate product caches
                        for item in order.items:
                            await self.cache_service.delete(CacheKeys.product(item.product_id))
                    
                    logger.info(
                        "Order payment completed successfully",
                        extra={
                            "order_id": order_id,
                            "total": float(order.total_price),
                            "items": len(order.items)
                        }
                    )
                    
                    return True
            
            except OperationalError as e:
                # Database deadlock or connection error - retry
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Database error, retrying in {wait_time}s: {e}",
                        extra={
                            "order_id": order_id,
                            "attempt": attempt + 1,
                            "max_retries": max_retries
                        }
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Max retries exceeded for order {order_id}",
                        exc_info=True
                    )
                    return False
            
            except ConcurrencyError as e:
                # Optimistic lock failure - retry
                logger.warning(f"Concurrency error: {e}, retrying")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                else:
                    return False
            
            except Exception as e:
                logger.error(
                    f"Unexpected error processing order {order_id}: {e}",
                    exc_info=True
                )
                return False
        
        return False


async def main():
    """Main entry point for the worker."""
    processor = OrderProcessor()
    
    try:
        await processor.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        await processor.stop()


if __name__ == "__main__":
    asyncio.run(main())
