"""
Domain Exceptions.

DECISION: Custom exception hierarchy
WHY:
  - Clear error semantics
  - Easy to map to HTTP status codes
  - Carry domain context

PATTERN: Exception hierarchy based on error type, not entity
"""

from typing import Any, Dict, Optional


class DomainException(Exception):
    """Base exception for all domain errors."""
    
    def __init__(
        self,
        message: str,
        code: str = "DOMAIN_ERROR",
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


# ============================================================================
# NOT FOUND ERRORS
# ============================================================================

class EntityNotFoundError(DomainException):
    """Entity was not found."""
    
    def __init__(
        self,
        entity_type: str,
        entity_id: Any,
        message: Optional[str] = None
    ):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(
            message=message or f"{entity_type} with id '{entity_id}' not found",
            code="NOT_FOUND",
            details={"entity_type": entity_type, "entity_id": str(entity_id)}
        )


class ProductNotFoundError(EntityNotFoundError):
    """Product not found."""
    
    def __init__(self, product_id: int):
        super().__init__("Product", product_id)


class OrderNotFoundError(EntityNotFoundError):
    """Order not found."""
    
    def __init__(self, order_id: str):
        super().__init__("Order", order_id)


# ============================================================================
# VALIDATION ERRORS
# ============================================================================

class ValidationError(DomainException):
    """Validation failed."""
    
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"field": field} if field else {}
        )


class InvalidQuantityError(ValidationError):
    """Invalid quantity value."""
    
    def __init__(self, quantity: int):
        super().__init__(
            message=f"Quantity must be positive, got {quantity}",
            field="quantity"
        )


class EmptyOrderError(ValidationError):
    """Order has no items."""
    
    def __init__(self):
        super().__init__(
            message="Order must have at least one item",
            field="items"
        )


# ============================================================================
# BUSINESS LOGIC ERRORS
# ============================================================================

class BusinessRuleViolation(DomainException):
    """Business rule was violated."""
    
    def __init__(self, message: str, rule: str):
        super().__init__(
            message=message,
            code="BUSINESS_RULE_VIOLATION",
            details={"rule": rule}
        )


class InsufficientStockError(BusinessRuleViolation):
    """Not enough stock available."""
    
    def __init__(
        self,
        product_id: int,
        product_name: str,
        requested: int,
        available: int
    ):
        self.product_id = product_id
        self.requested = requested
        self.available = available
        super().__init__(
            message=f"Insufficient stock for '{product_name}': requested {requested}, available {available}",
            rule="SUFFICIENT_STOCK"
        )
        self.details.update({
            "product_id": product_id,
            "product_name": product_name,
            "requested": requested,
            "available": available,
        })


class OrderAlreadyPaidError(BusinessRuleViolation):
    """Order has already been paid."""
    
    def __init__(self, order_id: str):
        super().__init__(
            message=f"Order {order_id} has already been paid",
            rule="ORDER_NOT_PAID"
        )
        self.details["order_id"] = order_id


class OrderNotPendingError(BusinessRuleViolation):
    """Order is not in pending status."""
    
    def __init__(self, order_id: str, current_status: str):
        super().__init__(
            message=f"Order {order_id} is not pending (status: {current_status})",
            rule="ORDER_PENDING"
        )
        self.details.update({
            "order_id": order_id,
            "current_status": current_status,
        })


class InvalidStatusTransitionError(BusinessRuleViolation):
    """Invalid order status transition."""
    
    def __init__(self, order_id: str, from_status: str, to_status: str):
        super().__init__(
            message=f"Cannot transition order {order_id} from {from_status} to {to_status}",
            rule="VALID_STATUS_TRANSITION"
        )
        self.details.update({
            "order_id": order_id,
            "from_status": from_status,
            "to_status": to_status,
        })


# ============================================================================
# CONCURRENCY ERRORS
# ============================================================================

class ConcurrencyError(DomainException):
    """Concurrent modification detected."""
    
    def __init__(self, message: str, entity_type: str, entity_id: Any):
        super().__init__(
            message=message,
            code="CONCURRENCY_ERROR",
            details={"entity_type": entity_type, "entity_id": str(entity_id)}
        )


class OptimisticLockError(ConcurrencyError):
    """Version mismatch during update."""
    
    def __init__(self, entity_type: str, entity_id: Any):
        super().__init__(
            message=f"{entity_type} {entity_id} was modified by another transaction",
            entity_type=entity_type,
            entity_id=entity_id
        )


class StockUpdateConflictError(ConcurrencyError):
    """Stock update failed due to concurrent modification."""
    
    def __init__(self, product_id: int):
        super().__init__(
            message=f"Stock update for product {product_id} failed due to concurrent modification",
            entity_type="Product",
            entity_id=product_id
        )


# ============================================================================
# IDEMPOTENCY ERRORS
# ============================================================================

class IdempotencyError(DomainException):
    """Idempotency related error."""
    pass


class DuplicatePaymentError(IdempotencyError):
    """Duplicate payment attempt detected."""
    
    def __init__(self, idempotency_key: str, existing_order_id: str):
        super().__init__(
            message=f"Payment with key '{idempotency_key}' already processed",
            code="DUPLICATE_PAYMENT",
            details={
                "idempotency_key": idempotency_key,
                "existing_order_id": existing_order_id,
            }
        )
