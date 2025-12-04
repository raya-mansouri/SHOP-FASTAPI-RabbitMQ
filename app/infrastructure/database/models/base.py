"""
SQLAlchemy Base Model Configuration.

DECISION: Custom base class with common fields
WHY: DRY principle - all models share id, created_at, updated_at
ALTERNATIVE: Mixins - more flexible but more complex
ALTERNATIVE: No base class - repetitive code
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    
    DECISION: Using DeclarativeBase (SQLAlchemy 2.0 style)
    WHY: Modern API, better type hints, cleaner syntax
    ALTERNATIVE: declarative_base() - old style, still works but deprecated patterns
    """
    
    # This allows type checkers to understand model attributes
    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """
        Auto-generate table name from class name.
        
        DECISION: Not using this - explicit table names are clearer
        WHY: Explicit is better than implicit for database schemas
        """
        # Convert CamelCase to snake_case
        # Example: OrderItem -> order_item
        import re
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        return name.replace('_model', '')


class BaseModel(Base):
    """
    Abstract base model with common fields.
    
    All domain models should inherit from this.
    """
    __abstract__ = True
    
    # DECISION: Using UUID for primary keys
    # WHY: 
    #   1. Globally unique - safe for distributed systems
    #   2. No sequential guessing (security)
    #   3. Can be generated client-side
    # ALTERNATIVE: Integer auto-increment
    #   - Simpler, faster joins
    #   - But: predictable, not distributed-safe
    # ALTERNATIVE: ULID
    #   - Time-sortable UUIDs
    #   - More complex to implement
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        index=True,
    )
    
    # DECISION: Using server_default for created_at
    # WHY: Database handles timestamp - consistent even with bulk inserts
    # ALTERNATIVE: Python default - can have clock skew issues
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,  # Often query by creation time
    )
    
    # DECISION: Using onupdate for updated_at
    # WHY: Automatically tracks modifications
    # NOTE: Only works with ORM updates, not raw SQL
    
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )
    
    def to_dict(self) -> dict[str, Any]:
        """
        Convert model to dictionary.
        
        DECISION: Simple dict conversion method
        WHY: Useful for debugging and simple serialization
        ALTERNATIVE: Use Pydantic model_dump() - do this in schemas instead
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<{self.__class__.__name__}(id={self.id})>"


class TimestampMixin:
    """
    Mixin for adding timestamp fields.
    
    DECISION: Also providing as mixin for flexibility
    WHY: Some models might inherit from different bases
    """
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )


class VersionMixin:
    """
    Mixin for optimistic locking.
    
    DECISION: Separate mixin for versioning
    WHY: Not all models need optimistic locking
    
    USAGE: Add to models that need concurrent update protection
    """
    
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Version for optimistic locking - increment on each update"
    )