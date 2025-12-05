"""
Redis Client Configuration.

DECISION: Using redis-py async client
WHY:
  - Native async support
  - Connection pooling built-in
  - Widely used, well documented

ALTERNATIVE: aioredis (deprecated, merged into redis-py)
"""

from typing import Optional
from redis.asyncio import ConnectionPool, Redis

from app.config import settings
 

class RedisClient:
    """
    Redis client manager.
    
    PATTERN: Singleton-like with connection pooling
    WHY: Reuse connections across requests
    """
    
    _pool: Optional[ConnectionPool] = None
    _client: Optional[Redis] = None
    
    @classmethod
    async def get_pool(cls) -> ConnectionPool:
        """Get or create connection pool."""
        if cls._pool is None:
            cls._pool = ConnectionPool.from_url(
                settings.redis_url,
                max_connections=20,
                decode_responses=True,  # Return strings, not bytes
            )
        return cls._pool
    
    @classmethod
    async def get_client(cls) -> Redis:
        """Get Redis client instance."""
        if cls._client is None:
            pool = await cls.get_pool()
            cls._client = Redis(connection_pool=pool)
        return cls._client
    
    @classmethod
    async def close(cls) -> None:
        """Close Redis connections."""
        if cls._client:
            await cls._client.close()
            cls._client = None
        if cls._pool:
            await cls._pool.disconnect()
            cls._pool = None
    
    @classmethod
    async def health_check(cls) -> bool:
        """Check Redis connection health."""
        try:
            client = await cls.get_client()
            await client.ping()
            return True
        except Exception:
            return False


# ============================================================================
# DEPENDENCY FOR FASTAPI
# ============================================================================

async def get_redis() -> Redis:
    """FastAPI dependency for Redis client."""
    return await RedisClient.get_client()