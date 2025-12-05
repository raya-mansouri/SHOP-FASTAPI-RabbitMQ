"""Domain layer - business logic and entities."""

from app.domain.exceptions import (
    BusinessRuleViolation,
    ConcurrencyError,
    DomainException,
    DuplicatePaymentError,
    EmptyOrderError,
    EntityNotFoundError,
    IdempotencyError,
    InsufficientStockError,
    InvalidQuantityError,
    InvalidStatusTransitionError,
    OptimisticLockError,
    OrderAlreadyPaidError,
    OrderNotFoundError,
    OrderNotPendingError,
    ProductNotFoundError,
    StockUpdateConflictError,
    ValidationError,
)

__all__ = [
    # Base
    "DomainException",
    # Not Found
    "EntityNotFoundError",
    "ProductNotFoundError",
    "OrderNotFoundError",
    # Validation
    "ValidationError",
    "InvalidQuantityError",
    "EmptyOrderError",
    # Business Rules
    "BusinessRuleViolation",
    "InsufficientStockError",
    "OrderAlreadyPaidError",
    "OrderNotPendingError",
    "InvalidStatusTransitionError",
    # Concurrency
    "ConcurrencyError",
    "OptimisticLockError",
    "StockUpdateConflictError",
    # Idempotency
    "IdempotencyError",
    "DuplicatePaymentError",
]
