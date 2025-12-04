from datetime import datetime

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditLogModel(Base):
    """
    Audit log for tracking important events.
    
    DECISION: Separate audit table
    WHY: 
      - Don't pollute domain tables
      - Easy to query/archive
      - Can be moved to separate database later
    
    ALTERNATIVE: Event sourcing
      - Pro: Complete history, replay capability
      - Con: Much more complex
    
    ALTERNATIVE: Database triggers
      - Pro: Captures all changes including raw SQL
      - Con: Hidden logic, harder to test
    """
    __tablename__ = "audit_logs"
    
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    
    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    
    entity_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    
    old_values: Mapped[str | None] = mapped_column(
        String,  # JSON string
        nullable=True,
    )
    
    new_values: Mapped[str | None] = mapped_column(
        String,  # JSON string
        nullable=True,
    )
    
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    
    ip_address: Mapped[str | None] = mapped_column(
        String(45),  # IPv6 max length
        nullable=True,
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_created", "created_at"),
    )