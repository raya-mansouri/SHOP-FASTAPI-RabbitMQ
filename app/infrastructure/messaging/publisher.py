"""
RabbitMQ Message Publisher.

PATTERN: Async publisher with connection management
WHY:
- Non-blocking message publishing
- Automatic reconnection
- Delivery confirmation
"""
import json
import logging
from typing import Any, Dict, Optional
from uuid import UUID

import aio_pika
from aio_pika import Message, DeliveryMode, ExchangeType
from aio_pika.abc import AbstractRobustConnection, AbstractChannel, AbstractExchange

from app.config import settings

logger = logging.getLogger(__name__)


class RabbitMQPublisher:
    """
    Async RabbitMQ publisher using aio-pika.
    
    FEATURES:
    - Robust connection with auto-reconnect
    - Publisher confirms
    - JSON message serialization
    """
    
    EXCHANGE_NAME = "orders"
    QUEUE_NAME = "order_processing"
    ROUTING_KEY = "order.payment"
    
    def __init__(self):
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[AbstractChannel] = None
        self._exchange: Optional[AbstractExchange] = None
    
    async def connect(self) -> None:
        """Initialize RabbitMQ connection."""
        try:
            self._connection = await aio_pika.connect_robust(
                settings.get_rabbitmq_url(),
                client_properties={"connection_name": "order-api-publisher"},
            )
            self._channel = await self._connection.channel()
            
            # Declare exchange
            self._exchange = await self._channel.declare_exchange(
                self.EXCHANGE_NAME,
                ExchangeType.DIRECT,
                durable=True,
            )
            
            # Declare queue
            queue = await self._channel.declare_queue(
                self.QUEUE_NAME,
                durable=True,
            )
            
            # Bind queue to exchange
            await queue.bind(self._exchange, self.ROUTING_KEY)
            
            logger.info("RabbitMQ publisher connected")
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close RabbitMQ connection."""
        if self._channel:
            await self._channel.close()
            self._channel = None
        if self._connection:
            await self._connection.close()
            self._connection = None
        logger.info("RabbitMQ publisher disconnected")
    
    async def publish_payment(
        self,
        order_id: UUID,
        idempotency_key: Optional[str] = None
    ) -> bool:
        """
        Publish payment processing message.
        
        ARGS:
            order_id: Order to process
            idempotency_key: Optional key for idempotent processing
        
        RETURNS:
            True if published successfully
        """
        if not self._exchange:
            logger.error("RabbitMQ not connected")
            return False
        
        try:
            message_body = {
                "order_id": str(order_id),
                "idempotency_key": idempotency_key,
            }
            
            message = Message(
                body=json.dumps(message_body).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            
            await self._exchange.publish(
                message,
                routing_key=self.ROUTING_KEY,
            )
            
            logger.info(f"Published payment message for order {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish payment message: {e}")
            return False
    
    async def publish_message(
        self,
        routing_key: str,
        body: Dict[str, Any]
    ) -> bool:
        """
        Publish generic message.
        
        ARGS:
            routing_key: Routing key for the message
            body: Message body as dict
        
        RETURNS:
            True if published successfully
        """
        if not self._exchange:
            logger.error("RabbitMQ not connected")
            return False
        
        try:
            message = Message(
                body=json.dumps(body).encode(),
                delivery_mode=DeliveryMode.PERSISTENT,
                content_type="application/json",
            )
            
            await self._exchange.publish(
                message,
                routing_key=routing_key,
            )
            
            logger.debug(f"Published message with routing key {routing_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Check RabbitMQ connection health."""
        try:
            if self._connection and not self._connection.is_closed:
                return True
            return False
        except Exception:
            return False


# Global publisher instance
rabbitmq_publisher = RabbitMQPublisher()


async def get_rabbitmq_publisher() -> RabbitMQPublisher:
    """FastAPI dependency for RabbitMQ publisher."""
    return rabbitmq_publisher
