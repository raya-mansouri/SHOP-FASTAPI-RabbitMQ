# tests/test_api.py
"""
API Integration Tests.

Tests the main API endpoints work correctly.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.infrastructure.database.session import get_db_session
from app.infrastructure.cache import get_cache_service
from app.infrastructure.messaging import get_rabbitmq_publisher


# Test database URL (use in-memory SQLite for tests)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


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
    
    # Override dependencies
    app.dependency_overrides[get_cache_service] = lambda: mock_cache_service
    app.dependency_overrides[get_rabbitmq_publisher] = lambda: mock_rabbitmq_publisher
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_check(test_client):
    """Test health check endpoint."""
    response = await test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_create_order_validation_error(test_client):
    """Test order creation with invalid data."""
    # Missing required fields
    response = await test_client.post("/orders", json={})
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_create_order_empty_items(test_client):
    """Test order creation with empty items."""
    response = await test_client.post(
        "/orders",
        json={
            "user_id": 1,
            "items": []
        }
    )
    assert response.status_code == 422  # Validation error - min_length=1


@pytest.mark.asyncio
async def test_get_nonexistent_order(test_client):
    """Test getting a non-existent order."""
    response = await test_client.get("/orders/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404