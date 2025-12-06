"""
Integration tests for order workflow.

Tests API validation and error handling without requiring full database setup.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock
from uuid import uuid4

from app.main import app
from app.infrastructure.cache import get_cache_service
from app.infrastructure.messaging import get_rabbitmq_publisher


@pytest.fixture
def mock_cache_service():
    """Mock cache service for tests."""
    mock = AsyncMock()
    mock.get_model.return_value = None
    mock.set_model.return_value = True
    mock.get_list.return_value = None
    mock.set_list.return_value = True
    mock.acquire_lock.return_value = True
    mock.release_lock.return_value = True
    mock.check_idempotency.return_value = None
    mock.set_idempotency.return_value = True
    mock.delete.return_value = True
    mock.delete_pattern.return_value = 0
    return mock


@pytest.fixture
def mock_rabbitmq_publisher():
    """Mock RabbitMQ publisher for tests."""
    mock = AsyncMock()
    mock.publish_payment.return_value = True
    return mock


@pytest.fixture
async def test_client(mock_cache_service, mock_rabbitmq_publisher):
    """Create test client with mocked dependencies."""
    app.dependency_overrides[get_cache_service] = lambda: mock_cache_service
    app.dependency_overrides[get_rabbitmq_publisher] = lambda: mock_rabbitmq_publisher
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_order_validation_errors(test_client):
    """Test various order validation scenarios."""
    
    # Test 1: Missing user_id
    response = await test_client.post(
        "/orders",
        json={"items": [{"product_id": 1, "quantity": 1}]}
    )
    assert response.status_code == 422
    
    # Test 2: Empty items
    response = await test_client.post(
        "/orders",
        json={"user_id": 1, "items": []}
    )
    assert response.status_code == 422
    
    # Test 3: Invalid quantity
    response = await test_client.post(
        "/orders",
        json={
            "user_id": 1,
            "items": [{"product_id": 1, "quantity": 0}]
        }
    )
    assert response.status_code == 422
    
    # Test 4: Duplicate products
    response = await test_client.post(
        "/orders",
        json={
            "user_id": 1,
            "items": [
                {"product_id": 1, "quantity": 1},
                {"product_id": 1, "quantity": 2},
            ]
        }
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_payment_endpoint_validation(test_client):
    """Test payment endpoint validation without database access."""
    
    # Test with invalid UUID format - should fail at validation level
    response = await test_client.post(
        "/orders/invalid-uuid/pay",
        json={"idempotency_key": "test-key"}
    )
    # Should return 422 for invalid UUID format
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_health_endpoint(test_client):
    """Test health check endpoint."""
    response = await test_client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
