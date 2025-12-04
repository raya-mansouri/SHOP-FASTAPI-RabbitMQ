"""
Database Session Management.

DECISION: Async SQLAlchemy with context managers
WHY: 
  - Non-blocking I/O for FastAPI
  - Proper connection cleanup
  - Transaction management

ALTERNATIVE: Sync SQLAlchemy
  - Simpler but blocks the event loop
  - Not suitable for async FastAPI
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, QueuePool

from app.config import settings


# ============================================================================
# ENGINE CONFIGURATION
# ============================================================================

# DECISION: Connection pooling strategy
# WHY: Reuse connections for better performance
# 
# Pool options:
# - QueuePool (default): Connection reuse, good for web apps
# - NullPool: No pooling, new connection each time (for serverless)
# - StaticPool: Single connection (for testing)

engine = create_async_engine(
    settings.database_url,
    
    # Pool configuration
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,       # Base connections
    max_overflow=settings.db_max_overflow,  # Extra connections
    pool_timeout=settings.db_pool_timeout,  # Wait for connection
    pool_recycle=settings.db_pool_recycle,  # Recycle stale connections
    pool_pre_ping=True,  # Verify connections before use
    
    # Logging
    echo=settings.db_echo,  # Log SQL (enable for debugging)
    echo_pool=False,        # Log pool events
    
    # Performance
    # DECISION: Using server-side prepared statements
    # WHY: Better performance for repeated queries
    connect_args={
        "prepared_statement_cache_size": 500,
        "statement_cache_size": 500,
    },
)


# ============================================================================
# SESSION FACTORY
# ============================================================================

# DECISION: Using async_sessionmaker (SQLAlchemy 2.0)
# WHY: Modern API, proper async support, type hints

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep objects usable after commit
    autoflush=False,         # Manual control over flushing
    autocommit=False,        # Explicit transaction control
)


# ============================================================================
# SESSION DEPENDENCY
# ============================================================================

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    
    USAGE:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    
    DECISION: Session-per-request pattern
    WHY: 
      - Each request gets isolated transaction
      - Automatic cleanup on request end
      - Prevents connection leaks
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database sessions (for workers/scripts).
    
    USAGE:
        async with get_db_session_context() as session:
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================================
# TRANSACTION HELPERS
# ============================================================================

@asynccontextmanager
async def transaction(session: AsyncSession):
    """
    Explicit transaction context manager.
    
    USAGE:
        async with transaction(session):
            # All operations here are in one transaction
            ...
    
    DECISION: Explicit transaction boundaries
    WHY: Clear code, predictable behavior
    """
    try:
        yield
        await session.commit()
    except Exception:
        await session.rollback()
        raise


# ============================================================================
# CONNECTION LIFECYCLE
# ============================================================================

async def init_db() -> None:
    """
    Initialize database connection pool.
    
    Call this on application startup.
    """
    # The pool is created lazily, but we can warm it up
    async with engine.begin() as conn:
        # Test connection
        await conn.execute(text("SELECT 1"))
    

async def close_db() -> None:
    """
    Close database connections.
    
    Call this on application shutdown.
    
    DECISION: Graceful shutdown
    WHY: Prevent connection leaks, allow in-flight queries to complete
    """
    await engine.dispose()


# ============================================================================
# TESTING SUPPORT
# ============================================================================

def create_test_engine(database_url: str):
    """
    Create engine for testing with NullPool.
    
    DECISION: NullPool for tests
    WHY: Each test gets fresh connection, no state leakage
    """
    return create_async_engine(
        database_url,
        poolclass=NullPool,
        echo=False,
    )