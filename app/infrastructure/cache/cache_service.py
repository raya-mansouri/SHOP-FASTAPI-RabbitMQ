"""
Cache Service - Redis Operations.

DECISION: Generic cache service with typed methods
WHY:
  - Reusable across different entities
  - Consistent serialization
  - Built-in TTL management
  - Error handling (cache should never break the app)

PATTERN: Cache-Aside (Lazy Loading)
  1. Check cache
  2. If miss, load from DB
  3. Store in cache
  4. Return data
"""

import json
import logging
from typing import Any, Callable, List, Optional, TypeVar

from redis.asyncio import Redis
from pydantic import BaseModel

from app.infrastructure.cache.keys import CacheKeys

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class CacheService:
    """
    Generic cache service for Redis operations.
    
    FEATURES:
    - JSON serialization for Pydantic models
    - TTL management
    - Pattern-based invalidation
    - Graceful degradation (cache errors don't break app)
    """
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    # ========================================================================
    # BASIC OPERATIONS
    # ========================================================================
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get raw value from cache.
        
        DECISION: Return None on error (graceful degradation)
        WHY: Cache miss is better than app failure
        """
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.warning(f"Cache GET error for {key}: {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: str,
        ttl: int = CacheKeys.TTL_MEDIUM
    ) -> bool:
        """
        Set value in cache with TTL.
        
        DECISION: Always use TTL
        WHY: Prevent stale data, automatic cleanup
        """
        try:
            await self.redis.set(key, value, ex=ttl)
            return True
        except Exception as e:
            logger.warning(f"Cache SET error for {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete single key."""
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache DELETE error for {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.
        
        DECISION: Using SCAN instead of KEYS
        WHY: KEYS blocks Redis, SCAN is non-blocking
        
        WARNING: Still use carefully in production
        """
        try:
            deleted = 0
            async for key in self.redis.scan_iter(match=pattern, count=100):
                await self.redis.delete(key)
                deleted += 1
            return deleted
        except Exception as e:
            logger.warning(f"Cache DELETE PATTERN error for {pattern}: {e}")
            return 0
    
    # ========================================================================
    # TYPED OPERATIONS (Pydantic Models)
    # ========================================================================
    
    async def get_model(
        self,
        key: str,
        model_class: type[T]
    ) -> Optional[T]:
        """
        Get and deserialize Pydantic model from cache.
        
        RETURNS: Model instance or None
        """
        data = await self.get(key)
        if data is None:
            return None
        
        try:
            return model_class.model_validate_json(data)
        except Exception as e:
            logger.warning(f"Cache deserialization error for {key}: {e}")
            # Invalid cache data - delete it
            await self.delete(key)
            return None
    
    async def set_model(
        self,
        key: str,
        model: BaseModel,
        ttl: int = CacheKeys.TTL_MEDIUM
    ) -> bool:
        """Serialize and cache Pydantic model."""
        try:
            data = model.model_dump_json()
            return await self.set(key, data, ttl)
        except Exception as e:
            logger.warning(f"Cache serialization error for {key}: {e}")
            return False
    
    async def get_list(
        self,
        key: str,
        model_class: type[T]
    ) -> Optional[List[T]]:
        """Get list of models from cache."""
        data = await self.get(key)
        if data is None:
            return None
        
        try:
            items = json.loads(data)
            return [model_class.model_validate(item) for item in items]
        except Exception as e:
            logger.warning(f"Cache list deserialization error for {key}: {e}")
            await self.delete(key)
            return None
    
    async def set_list(
        self,
        key: str,
        models: List[BaseModel],
        ttl: int = CacheKeys.TTL_MEDIUM
    ) -> bool:
        """Cache list of Pydantic models."""
        try:
            data = json.dumps([m.model_dump() for m in models])
            return await self.set(key, data, ttl)
        except Exception as e:
            logger.warning(f"Cache list serialization error for {key}: {e}")
            return False
    
    # ========================================================================
    # CACHE-ASIDE PATTERN
    # ========================================================================
    
    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int = CacheKeys.TTL_MEDIUM
    ) -> Any:
        """
        Get from cache or execute factory and cache result.
        
        PATTERN: Cache-Aside (Lazy Loading)
        
        USAGE:
            result = await cache.get_or_set(
                key="product:list",
                factory=lambda: db.get_all_products(),
                ttl=300
            )
        """
        # Try cache first
        cached = await self.get(key)
        if cached is not None:
            return json.loads(cached)
        
        # Cache miss - execute factory
        result = await factory() if callable(factory) else factory
        
        # Store in cache
        await self.set(key, json.dumps(result), ttl)
        
        return result
    
    # ========================================================================
    # DISTRIBUTED LOCKING
    # ========================================================================
    
    async def acquire_lock(
        self,
        lock_key: str,
        ttl: int = 30,
        blocking: bool = False,
        timeout: int = 10
    ) -> bool:
        """
        Acquire distributed lock.
        
        DECISION: Using SET NX (atomic)
        WHY: Simple, reliable, no race conditions
        
        PATTERN: Distributed Lock with TTL
        - Lock auto-expires (prevents deadlocks)
        - Only one process can hold lock
        
        PARAMETERS:
        - lock_key: Unique key for the lock
        - ttl: Lock expiration in seconds
        - blocking: If True, wait for lock
        - timeout: Max wait time if blocking
        
        RETURNS: True if lock acquired
        """
        try:
            if blocking:
                # Blocking lock - retry until timeout
                import asyncio
                end_time = asyncio.get_event_loop().time() + timeout
                while asyncio.get_event_loop().time() < end_time:
                    if await self.redis.set(lock_key, "1", nx=True, ex=ttl):
                        return True
                    await asyncio.sleep(0.1)
                return False
            else:
                # Non-blocking - single attempt
                result = await self.redis.set(lock_key, "1", nx=True, ex=ttl)
                return result is True
        except Exception as e:
            logger.warning(f"Lock acquire error for {lock_key}: {e}")
            return False
    
    async def release_lock(self, lock_key: str) -> bool:
        """Release distributed lock."""
        return await self.delete(lock_key)
    
    # ========================================================================
    # IDEMPOTENCY
    # ========================================================================
    
    async def check_idempotency(
        self,
        idempotency_key: str
    ) -> Optional[dict]:
        """
        Check if operation was already performed.
        
        RETURNS: Previous result if exists, None if new operation
        """
        key = CacheKeys.idempotency(idempotency_key)
        data = await self.get(key)
        if data:
            return json.loads(data)
        return None
    
    async def set_idempotency(
        self,
        idempotency_key: str,
        result: dict
    ) -> bool:
        """
        Store operation result for idempotency.
        
        TTL: 24 hours (standard for payment idempotency)
        """
        key = CacheKeys.idempotency(idempotency_key)
        return await self.set(
            key,
            json.dumps(result),
            ttl=CacheKeys.TTL_IDEMPOTENCY
        )


# ============================================================================
# FACTORY
# ============================================================================

def create_cache_service(redis: Redis) -> CacheService:
    """Factory for cache service."""
    return CacheService(redis)
