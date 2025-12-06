# app/infrastructure/database/session.py
"""
Database Session Management.

PATTERN: Async session factory with proper lifecycle
WHY:
- Ensures proper connection pooling
- Handles session cleanup
- Supports dependency injection in FastAPI
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import settings


# Create async engine
engine = create_async_engine(
    settings.get_database_url(),
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,  # Verify connections before use
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database session.
    
    USAGE:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
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


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session (for use outside FastAPI).
    
    USAGE:
        async with get_db_context() as session:
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


class DatabaseSessionManager:
    """
    Manager for database sessions with lifecycle control.
    Used for startup/shutdown events.
    """
    
    def __init__(self):
        self._engine = engine
        self._sessionmaker = AsyncSessionLocal
    
    async def close(self):
        """Close database connections."""
        await self._engine.dispose()
    
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a session with proper lifecycle management."""
        async with self._sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a session with explicit transaction control."""
        async with self._sessionmaker() as session:
            async with session.begin():
                yield session


# Global session manager instance
sessionmanager = DatabaseSessionManager()
