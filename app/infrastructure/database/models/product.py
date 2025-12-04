from decimal import Decimal
from typing import TYPE_CHECKING, List

from sqlalchemy import (
    CheckConstraint,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel

if TYPE_CHECKING:
    from .order import OrderItemModel

class ProductModel(BaseModel):
    """
    Product entity.
    
    INDEXES:
    - Primary key (id) - auto-indexed
    - name - for search queries
    - stock - for low-stock monitoring queries
    - created_at - inherited, for sorting
    
    CONSTRAINTS:
    - price > 0: Products must have positive price
    - stock >= 0: Stock cannot go negative
    """
    __tablename__ = "products"
    
    # Using Integer for ID as per requirements (simpler for products)
    # DECISION: Override UUID with Integer for products
    # WHY: Products are master data, don't need distributed IDs
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    price: Mapped[Decimal] = mapped_column(
        Integer,
        nullable=False,
        doc="Product price"
    )
    
    stock: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Available stock quantity"
    )
    
    # Optimistic locking version
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Version for optimistic locking"
    )

    
    # Relationships
    order_items: Mapped[List["OrderItemModel"]] = relationship(
        "OrderItemModel",
        back_populates="product",
        lazy="noload",  # Don't load by default - usually not needed
    )
    
    __table_args__ = (
        # CheckConstraint("price > 0", name="ck_product_positive_price"),
        CheckConstraint("stock >= 0", name="ck_product_non_negative_stock"),
        Index("ix_product_stock", "stock"),  # For low-stock queries
    )
    
    def has_sufficient_stock(self, quantity: int) -> bool:
        """Check if enough stock is available."""
        return self.stock >= quantity
    
    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', stock={self.stock})>"