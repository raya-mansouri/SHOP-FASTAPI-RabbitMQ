from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey,
    CheckConstraint, Index, Enum as SQLEnum
)
from sqlalchemy.sql import func

from app.infrastructure.database.models.base import BaseModel



class AuditLogModel(BaseModel):
    """
    Audit log for tracking important events.
    Optional but recommended for production systems.
    """
    
    __tablename__ = "audit_logs"
    
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False)
    user_id = Column(Integer, nullable=True)
    changes = Column(String, nullable=True)  # JSON string
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True
    ) 
    # TODO: check createed_at index performance impact and conflict with BaseModel
    __table_args__ = (
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_created", "created_at"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<AuditLog(entity={self.entity_type}:{self.entity_id}, "
            f"action={self.action})>"
        )