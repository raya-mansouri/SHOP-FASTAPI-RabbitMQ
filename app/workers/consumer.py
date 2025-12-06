"""
RabbitMQ Consumer - Alternative implementation.

This is an alternative to order_processor.py.
Use this if you prefer a more modular approach.
"""

import asyncio
import json
import logging
from typing import Callable

from aio_pika import IncomingMessage
from aio_pika.abc import AbstractConnection, AbstractChannel

from app.config import settings
from app.infrastructure.messaging.rabbitmq_client import RabbitMQClient

logger = logging.getLogger(__name__)


class RabbitMQConsumer:
    """
    Generic RabbitMQ consumer.

    This can be used as an alternative to the order_processor.py
    if you want a more generic consumer pattern.
    """

    def __init__(self, message_handler: Callable[[dict], None]):
        self.message_handler = message_handler
        self.connection: AbstractConnection | None = None
        self.channel: AbstractChannel | None = None
        self.running = False

    async def start(self):
        """Start consuming messages."""
        # Connect to RabbitMQ
        # Implementation would be similar to order_processor.py
        # For now, this is a placeholder
        logger.info("RabbitMQ consumer started (placeholder)")
        self.running = True

    async def stop(self):
        """Stop consuming."""
        self.running = False
        if self.connection:
            await self.connection.close()
        logger.info("RabbitMQ consumer stopped")

    async def _process_message(self, message: IncomingMessage):
        """Process incoming message."""
        async with message.process():
            try:
                body = json.loads(message.body.decode())
                await self.message_handler(body)
                await message.ack()
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                await message.reject(requeue=True)
