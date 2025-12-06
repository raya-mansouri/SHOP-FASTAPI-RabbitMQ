"""
Pytest Configuration and Fixtures.
"""
import pytest
import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from httpx import AsyncClient

from app.infrastructure.database.models import Base


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://orderuser:orderpass@localhost:5432/orders_db"


# Use pytest-asyncio's default event_loop fixture
# No need to override it - pytest-asyncio handles it properly


@pytest.fixture(scope="function")
async def async_engine():
    """Create async database engine for tests."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async session for e2e tests."""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        yield session


@pytest.fixture
async def e2e_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for E2E tests with full dependencies."""
    from app.main import app
    from app.infrastructure.cache.redis_client import redis_manager
    from app.infrastructure.messaging.publisher import rabbitmq_publisher
    from app.infrastructure.database.session import sessionmanager
    
    # Initialize dependencies
    try:
        await redis_manager.connect()
        await rabbitmq_publisher.connect()
    except Exception as e:
        # If Redis/RabbitMQ aren't available, skip gracefully
        import pytest
        pytest.skip(f"Required services not available: {e}")
    
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            yield client
    finally:
        # Cleanup - ensure all connections are closed
        try:
            await rabbitmq_publisher.disconnect()
            await redis_manager.disconnect()
            await sessionmanager.close()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """Reset dependency overrides after each test."""
    from app.main import app
    yield
    app.dependency_overrides.clear()