from sqlalchemy import (
    Column, Integer, String, PositiveInteger,
    CheckConstraint, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.models.base import BaseModel



class ProductModel(BaseModel):
    """Product table model."""
    
    __tablename__ = "products"
    
    name = Column(String(255), nullable=False, index=True)
    price = Column(
        PositiveInteger, 
        nullable=False,
        doc="Product price"
    )
    stock = Column(
        Integer, 
        nullable=False, 
        default=0,
        doc="Available stock quantity"
    )
    version = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Version for optimistic locking"
    )

    
    # Relationships
    order_items = relationship("OrderItemModel", back_populates="product")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("price > 0", name="positive_price"),
        CheckConstraint("stock >= 0", name="non_negative_stock"),
        Index("idx_product_stock", "stock"),  # For low stock queries
        Index("idx_product_created", "created_at"),
    )
    
    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', stock={self.stock})>"