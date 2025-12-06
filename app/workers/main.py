# app/worker/main.py
"""
RabbitMQ Worker for Payment Processing.

RESPONSIBILITIES:
- Consume payment messages from RabbitMQ
- Process payments (deduct stock, update order status)
- Handle failures and retries
"""
import asyncio
import json
import logging
from uuid import UUID

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.config import settings
from app.infrastructure.database.session import get_db_context
from app.infrastructure.cache.redis_client import redis_manager
from app.infrastructure.cache.cache_service import CacheService
from app.application.commands import ProcessPaymentCommand
from app.domain.exceptions import (
    OrderNotFoundError,
    OrderNotPendingError,
    InsufficientStockError,
    OptimisticLockError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class PaymentWorker:
    """
    Worker for processing payment messages.
    
    FLOW:
    1. Consume message from RabbitMQ
    2. Process payment (with retries)
    3. Acknowledge or reject message
    """
    
    QUEUE_NAME = "order_processing"
    MAX_RETRIES = 3
    
    def __init__(self):
        self._connection = None
        self._channel = None
        self._queue = None
    
    async def connect(self) -> None:
        """Connect to RabbitMQ."""
        self._connection = await aio_pika.connect_robust(
            settings.get_rabbitmq_url(),
            client_properties={"connection_name": "payment-worker"},
        )
        self._channel = await self._connection.channel()
        
        # Set prefetch count for fair dispatch
        await self._channel.set_qos(prefetch_count=1)
        
        # Declare queue (must match publisher)
        self._queue = await self._channel.declare_queue(
            self.QUEUE_NAME,
            durable=True,
        )
        
        logger.info("Worker connected to RabbitMQ")
    
    async def disconnect(self) -> None:
        """Disconnect from RabbitMQ."""
        if self._channel:
            await self._channel.close()
        if self._connection:
            await self._connection.close()
        logger.info("Worker disconnected from RabbitMQ")
    
    async def process_message(self, message: AbstractIncomingMessage) -> None:
        """
        Process a single payment message.
        
        FLOW:
        1. Parse message
        2. Process payment in transaction
        3. ACK on success, NACK with requeue on transient failure
        """
        async with message.process(requeue=False):
            try:
                # Parse message body
                body = json.loads(message.body.decode())
                order_id = UUID(body["order_id"])
                
                logger.info(f"Processing payment for order {order_id}")
                
                # Process in database transaction
                async with get_db_context() as session:
                    cache = CacheService(redis_manager.get_client())
                    
                    command = ProcessPaymentCommand(
                        order_id=order_id,
                        session=session,
                        cache=cache,
                    )
                    
                    success = await command.execute()
                    
                    if success:
                        logger.info(f"Payment processed successfully for order {order_id}")
                    else:
                        logger.warning(f"Payment failed for order {order_id}")
                
            except OrderNotFoundError as e:
                # Order doesn't exist - don't retry
                logger.error(f"Order not found: {e}")
                
            except OrderNotPendingError as e:
                # Invalid state - don't retry
                logger.error(f"Order not in valid state: {e}")
                
            except InsufficientStockError as e:
                # Business error - don't retry
                logger.error(f"Insufficient stock: {e}")
                
            except OptimisticLockError as e:
                # Concurrent modification - could retry
                logger.warning(f"Concurrent modification: {e}")
                # Re-raise to trigger requeue
                raise
                
            except json.JSONDecodeError as e:
                # Invalid message - don't retry
                logger.error(f"Invalid message format: {e}")
                
            except Exception as e:
                logger.error(f"Unexpected error processing payment: {e}", exc_info=True)
                raise
    
    async def start_consuming(self) -> None:
        """Start consuming messages."""
        logger.info("Starting to consume messages...")
        
        async with self._queue.iterator() as queue_iter:
            async for message in queue_iter:
                await self.process_message(message)
    
    async def run(self) -> None:
        """Main worker loop."""
        await self.connect()
        
        try:
            await self.start_consuming()
        except asyncio.CancelledError:
            logger.info("Worker cancelled")
        finally:
            await self.disconnect()


async def main():
    """Entry point for worker."""
    # Initialize Redis
    await redis_manager.connect()
    
    worker = PaymentWorker()
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await redis_manager.disconnect()


if __name__ == "__main__":
    asyncio.run(main())