from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, PositiveInteger, UUID, ForeignKey,
    CheckConstraint, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship

from app.infrastructure.database.models.base import BaseModel

# TODO: replace enum with table, because: changing enums field is overhead in DB migrations
class OrderStatus(str, SQLEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"


class OrderModel(BaseModel):
    """Order table model."""
    
    __tablename__ = "orders"
    
    user_id = Column(
        Integer,
        nullable=False,
        index=True,
        doc="User who created the order"
    )
    status = Column(
        SQLEnum(OrderStatus),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True
    )
    total_price = Column(
        PositiveInteger,
        nullable=False,
        default=0
    )
    idempotency_key = Column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
        doc="Key for idempotent payment operations"
    )
    version = Column(
        Integer,
        nullable=False,
        default=0,
        doc="Version for optimistic locking"
    )

    
    # Relationships
    items = relationship(
        "OrderItemModel",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin"  # Eager loading to avoid N+1
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint("total_price >= 0", name="non_negative_total"),
        CheckConstraint("user_id > 0", name="positive_user_id"),
        Index("idx_order_user_status", "user_id", "status"),
        Index("idx_order_status_created", "status", "created_at"),
    )
    
    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, user_id={self.user_id}, "
            f"status={self.status}, total={self.total_price})>"
        )
        



class OrderItemModel(BaseModel):
    """Order item table model."""
    
    __tablename__ = "order_items"
    
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True
    )
    quantity = Column(
        Integer,
        nullable=False,
        doc="Quantity ordered"
    )
    unit_price = Column(
        PositiveInteger,
        nullable=False,
        doc="Price at time of order (historical)"
    )
    
    # Relationships
    order = relationship("OrderModel", back_populates="items")
    product = relationship("ProductModel", back_populates="order_items")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="non_negative_price"),
        Index("idx_order_item_lookup", "order_id", "product_id"),
    )
    
    @property
    def subtotal(self) -> Decimal:
        """Calculate subtotal for this order item."""
        return self.unit_price * self.quantity
    
    def __repr__(self) -> str:
        return (
            f"<OrderItem(id={self.id}, order_id={self.order_id}, "
            f"product_id={self.product_id}, qty={self.quantity})>"
        )

