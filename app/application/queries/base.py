"""
Query Base Classes.

PATTERN: Query in CQRS
WHY:
  - Read operations separated from writes
  - Can use different data source (cache, read replica)
  - Optimized for read performance
  
DECISION: Queries check cache first, fallback to database
WHY: Redis for speed, PostgreSQL as source of truth
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional

# Type variable for query result
TResult = TypeVar("TResult")


class Query(ABC, Generic[TResult]):
    """
    Base class for all queries.
    
    Queries represent requests for data.
    They are read operations and should NOT modify state.
    
    CACHING STRATEGY:
    1. Check Redis cache
    2. If cache hit, return cached data
    3. If cache miss, query PostgreSQL
    4. Store result in Redis
    5. Return data
    """
    
    @abstractmethod
    async def execute(self) -> TResult:
        """Execute the query and return result."""
        pass


class CachedQuery(Query[TResult]):
    """
    Query with built-in caching logic.
    
    Subclasses implement:
    - get_cache_key(): Return cache key for this query
    - fetch_from_db(): Fetch data from database
    - get_ttl(): Return cache TTL
    """
    
    @abstractmethod
    def get_cache_key(self) -> str:
        """Return cache key for this query."""
        pass
    
    @abstractmethod
    async def fetch_from_db(self) -> TResult:
        """Fetch data from database (cache miss)."""
        pass
    
    def get_ttl(self) -> int:
        """Return TTL for cached data. Override if needed."""
        from app.infrastructure.cache import CacheKeys
        return CacheKeys.TTL_MEDIUM