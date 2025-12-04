from sqlalchemy import Column, DateTime, func, UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class BaseModel(Base):
    __abstract__ = True

    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        index=True, 
        autoincrement=True
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now()
    )