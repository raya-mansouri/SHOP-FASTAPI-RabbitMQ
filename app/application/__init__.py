"""
Application Layer - CQRS Implementation.

ARCHITECTURE:
- Commands: Write operations (PostgreSQL)
- Queries: Read operations (Redis -> PostgreSQL)
- Schemas: DTOs for API communication

DECISION: Full CQRS with separate read/write paths
WHY:
  - Redis for fast reads
  - PostgreSQL for durable writes
  - Clear separation of concerns
  - Independent scaling of read/write
"""


# Commands
from app.application.commands import (
    Command,
    CommandResult,
    CreateOrderCommand,
    InitiatePaymentCommand,
    ProcessPaymentCommand,
)

# Queries
from app.application.queries import (
    Query,
    GetProductsQuery,
    GetProductByIdQuery,
    GetOrderByIdQuery,
    GetUserOrdersQuery,
)

__all__ = [
    # Commands
    "Command",
    "CommandResult",
    "CreateOrderCommand",
    "InitiatePaymentCommand",
    "ProcessPaymentCommand",
    # Queries
    "Query",
    "GetProductsQuery",
    "GetProductByIdQuery",
    "GetOrderByIdQuery",
    "GetUserOrdersQuery",
]