#!/usr/bin/env python3
"""
Test script to verify RabbitMQ publisher and consumer are working.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.infrastructure.messaging.publisher import RabbitMQPublisher
from app.config import settings
from uuid import uuid4


async def test_connection():
    """Test RabbitMQ connection and message publishing."""
    print("=" * 60)
    print("RabbitMQ Connection Test")
    print("=" * 60)
    
    # Print configuration
    print(f"\nConfiguration:")
    print(f"  RabbitMQ URL: {settings.get_rabbitmq_url()}")
    print(f"  Exchange: {settings.rabbitmq_exchange_name}")
    print(f"  Queue: {settings.rabbitmq_queue_name}")
    print(f"  Routing Key: {settings.rabbitmq_routing_key}")
    
    # Initialize publisher
    publisher = RabbitMQPublisher()
    
    try:
        print("\n[1/3] Connecting to RabbitMQ...")
        await publisher.connect()
        print("✓ Connected successfully")
        
        print("\n[2/3] Checking health...")
        is_healthy = await publisher.health_check()
        if is_healthy:
            print("✓ Connection is healthy")
        else:
            print("✗ Connection is not healthy")
            return False
        
        print("\n[3/3] Publishing test message...")
        test_order_id = uuid4()
        success = await publisher.publish_payment(
            order_id=test_order_id,
            user_id=1,
            idempotency_key="test-key-123"
        )
        
        if success:
            print(f"✓ Test message published for order {test_order_id}")
            print("\nNow check if the worker consumes this message.")
            print("Run: docker logs order_worker -f")
        else:
            print("✗ Failed to publish message")
            return False
        
        print("\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        print("\nDisconnecting...")
        await publisher.disconnect()


if __name__ == "__main__":
    result = asyncio.run(test_connection())
    sys.exit(0 if result else 1)
