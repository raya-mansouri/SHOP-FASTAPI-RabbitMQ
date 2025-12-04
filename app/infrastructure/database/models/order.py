from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseModel

if TYPE_CHECKING:
    from .product import ProductModel


class OrderStatus(str, Enum):
    """
    Order status enumeration.
    
    DECISION: Using Python Enum with str mixin
    WHY: 
      - Type safety in Python code
      - String values for readability in database
      - JSON serialization works automatically
    
    ALTERNATIVE: Database enum type
      - Pro: Strict database-level validation
      - Con: Harder to modify (requires migration)
    
    ALTERNATIVE: Status table with foreign key
      - Pro: Easy to add statuses, can store metadata
      - Con: Extra join for every query
    
    For this project: Python Enum is sufficient. If we needed to add
    status metadata (display_name, allowed_transitions), use a table.
    """
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"  # Added: when worker picks up
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"    # Added: for order cancellation
    
    @classmethod
    def terminal_statuses(cls) -> set["OrderStatus"]:
        """Statuses that cannot be changed."""
        return {cls.PAID, cls.FAILED, cls.CANCELLED}
    
    def can_transition_to(self, new_status: "OrderStatus") -> bool:
        """
        Check if status transition is valid.
        
        DECISION: Encoding state machine in enum
        WHY: Business logic stays with the domain model
        """
        valid_transitions = {
            OrderStatus.PENDING: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
            OrderStatus.PROCESSING: {OrderStatus.PAID, OrderStatus.FAILED},
            OrderStatus.PAID: set(),      # Terminal
            OrderStatus.FAILED: {OrderStatus.PENDING},  # Allow retry
            OrderStatus.CANCELLED: set(), # Terminal
        }
        return new_status in valid_transitions.get(self, set())


class OrderModel(BaseModel):
    """
    Order entity - the aggregate root for order management.
    
    DECISION: UUID for order IDs
    WHY: 
      - Orders may be created from multiple services
      - Security - can't guess order IDs
      - Can be used in external systems (payment gateway, shipping)
    
    INDEXES:
    - user_id + status: Common query pattern
    - status + created_at: For order processing queues
    - idempotency_key: For duplicate detection
    """
    __tablename__ = "orders"
    
    user_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        doc="User who created the order"
    )
    
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, name="order_status_enum", create_constraint=True),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True,
    )
    
    # DECISION: Store total_price on order (denormalization)
    # WHY: 
    #   - Avoid recalculating on every read
    #   - Historical accuracy (prices may change)
    # ALTERNATIVE: Calculate from items
    #   - Pro: Always accurate
    #   - Con: Performance hit, complex with historical prices
    total_price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    
    # DECISION: Idempotency key for payment
    # WHY: Prevents duplicate payments on retry
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        index=True,
    )
    
    # Error tracking
    failure_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Version for optimistic locking"
    )
    
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # Relationships
    # DECISION: Using selectin loading for items
    # WHY: 
    #   - Prevents N+1 queries
    #   - More efficient than joined for 1-to-many
    #   - Items are almost always needed with order
    items: Mapped[List["OrderItemModel"]] = relationship(
        "OrderItemModel",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin", # Eager loading to avoid N+1
        order_by="OrderItemModel.id",
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint("total_price >= 0", name="non_negative_total"),
        CheckConstraint("user_id > 0", name="positive_user_id"),
        Index("idx_order_user_status", "user_id", "status"),
        Index("idx_order_status_created", "status", "created_at"),
    )
    
    @property
    def is_terminal(self) -> bool:
        """Check if order is in a terminal state."""
        return self.status in OrderStatus.terminal_statuses()
    
    @property
    def can_be_paid(self) -> bool:
        """Check if order can transition to payment."""
        return self.status == OrderStatus.PENDING
    
    def calculate_total(self) -> int:
        """Calculate total from items."""
        return sum(
            (item.unit_price * item.quantity for item in self.items),
            0
        )
    
    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, user_id={self.user_id}, "
            f"status={self.status}, total={self.total_price})>"
        )
        



class OrderItemModel(BaseModel):
    """
    Order line item.
    
    DECISION: Store unit_price at time of order
    WHY: Product prices change, but order should reflect purchase price
    
    This is a standard e-commerce pattern called "historical pricing"
    """
    __tablename__ = "order_items"
    
    order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.id", ondelete="RESTRICT"),  # Don't delete products with orders
        nullable=False,
        index=True,
    )
    
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Quantity ordered"
    )
    
    unit_price: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Price at time of order (historical)"
    )
    
    # Relationships
    order: Mapped["OrderModel"] = relationship(
        "OrderModel",
        back_populates="items",
    )
    
    product: Mapped["ProductModel"] = relationship(
        "ProductModel",
        back_populates="order_items",
        lazy="joined",  # Usually need product info with item
    )
    
    __table_args__ = (
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="non_negative_price"),
        Index("idx_order_item_lookup", "order_id", "product_id"),
    )
    
    @property
    def subtotal(self) -> int:
        """Calculate subtotal for this order item."""
        return self.unit_price * self.quantity
    
    def __repr__(self) -> str:
        return (
            f"<OrderItem(id={self.id}, order_id={self.order_id}, "
            f"product_id={self.product_id}, qty={self.quantity})>"
        )

