"""
Database infrastructure module.

Exports commonly used components.
"""

from app.infrastructure.database.models import (
    AuditLogModel,
    OrderItemModel,
    OrderModel,
    OrderStatus,
    ProductModel,
    Base,
    BaseModel
)
from app.infrastructure.database.session import (
    engine,
    AsyncSessionLocal,
    get_db_session,
    get_db_context,
    sessionmanager,
    DatabaseSessionManager,
)
from app.infrastructure.database.repositories import (
    ProductRepository,
    OrderRepository,
    RepositoryFactory,
    get_repositories,
)

__all__ = [
    # Base
    "Base",
    "BaseModel",
    # Models
    "ProductModel",
    "OrderModel",
    "OrderItemModel",
    "AuditLogModel",
    "OrderStatus",
    # Session
    "engine",
    "AsyncSessionLocal",
    "get_db_session",
    "get_db_context",
    "sessionmanager",
    "DatabaseSessionManager",
    # Repositories
    "ProductRepository",
    "OrderRepository",
    "RepositoryFactory",
    "get_repositories",
]
