# app/infrastructure/cache/redis_client.py
"""
Redis Client Management.

PATTERN: Singleton connection with dependency injection
WHY:
- Single connection pool for efficiency
- Proper lifecycle management
- Easy dependency injection in FastAPI
"""
import logging
from typing import AsyncGenerator, Optional

from redis.asyncio import Redis, ConnectionPool

from app.config import settings
from app.infrastructure.cache.cache_service import CacheService

logger = logging.getLogger(__name__)


class RedisManager:
    """Manager for Redis connections."""
    
    def __init__(self):
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[Redis] = None
    
    async def connect(self) -> None:
        """Initialize Redis connection pool."""
        if self._pool is None:
            self._pool = ConnectionPool.from_url(
                settings.get_redis_url(),
                max_connections=20,
                decode_responses=True,
            )
            self._redis = Redis(connection_pool=self._pool)
            logger.info("Redis connection pool initialized")
    
    async def disconnect(self) -> None:
        """Close Redis connections."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None
        logger.info("Redis connection pool closed")
    
    def get_client(self) -> Redis:
        """Get Redis client."""
        if self._redis is None:
            raise RuntimeError("Redis not initialized. Call connect() first.")
        return self._redis
    
    async def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            if self._redis:
                await self._redis.ping()
                return True
            return False
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False


# Global Redis manager instance
redis_manager = RedisManager()


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency for Redis client."""
    yield redis_manager.get_client()


async def get_cache_service() -> AsyncGenerator[CacheService, None]:
    """FastAPI dependency for CacheService."""
    redis = redis_manager.get_client()
    yield CacheService(redis)