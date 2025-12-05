"""
Application Layer Schemas (DTOs - Data Transfer Objects).

DECISION: Separate schemas from SQLAlchemy models
WHY:
  - API contracts independent of database structure
  - Validation at application boundary
  - Can evolve API without changing database
  
ALTERNATIVE: Use SQLAlchemy models directly
  - Simpler but couples API to database
  - Changes to DB affect API (breaking changes)
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# PRODUCT SCHEMAS
# ============================================================================

class ProductBase(BaseModel):
    """Base product fields."""
    name: str = Field(..., min_length=1, max_length=255)
    price: int = Field(..., gt=0)
    stock: int = Field(..., ge=0)


class ProductCreate(ProductBase):
    """Schema for creating a product."""
    pass


class ProductResponse(ProductBase):
    """Schema for product in responses."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True  # Allow from ORM model


class ProductListResponse(BaseModel):
    """Schema for list of products."""
    items: List[ProductResponse]
    total: int
    skip: int
    limit: int


# ============================================================================
# ORDER ITEM SCHEMAS
# ============================================================================

class OrderItemCreate(BaseModel):
    """Schema for creating an order item."""
    product_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0, le=100)  # Max 100 per item
    
    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Quantity must be positive")
        return v


class OrderItemResponse(BaseModel):
    """Schema for order item in responses."""
    id: UUID
    product_id: int
    product_name: Optional[str] = None  # Denormalized for convenience
    quantity: int
    unit_price: int
    subtotal: int
    
    class Config:
        from_attributes = True


# ============================================================================
# ORDER SCHEMAS
# ============================================================================

class OrderCreate(BaseModel):
    """
    Schema for creating an order.
    
    VALIDATION:
    - user_id must be positive
    - items must not be empty
    - items must have unique product_ids (no duplicates)
    """
    user_id: int = Field(..., gt=0)
    items: List[OrderItemCreate] = Field(..., min_length=1, max_length=50)
    
    @model_validator(mode="after")
    def validate_unique_products(self) -> "OrderCreate":
        """Ensure no duplicate product IDs."""
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Duplicate product IDs in order items")
        return self


class OrderResponse(BaseModel):
    """Schema for order in responses."""
    id: UUID
    user_id: int
    status: str
    total_price: int
    items: List[OrderItemResponse]
    created_at: datetime
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    
    class Config:
        from_attributes = True


class OrderCreateResponse(BaseModel):
    """Response after creating an order."""
    id: UUID
    status: str
    message: str = "Order created successfully"


class OrderListResponse(BaseModel):
    """Schema for list of orders."""
    items: List[OrderResponse]
    total: int
    skip: int
    limit: int


# ============================================================================
# PAYMENT SCHEMAS
# ============================================================================

class PaymentRequest(BaseModel):
    """
    Schema for payment request.
    
    DECISION: Idempotency key is optional but recommended
    WHY: Allows client to safely retry payment requests
    """
    idempotency_key: Optional[str] = Field(
        None,
        min_length=1, 
        max_length=255,
        description="Unique key to prevent duplicate payments"
    )


class PaymentResponse(BaseModel):
    """Response after initiating payment."""
    order_id: UUID
    status: str
    message: str


# ============================================================================
# ERROR SCHEMAS
# ============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    details: Optional[dict] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response."""
    error: str = "VALIDATION_ERROR"
    message: str = "Validation failed"
    details: List[dict]
