"""Queries module - Read operations with caching."""

from app.application.queries.base import Query, CachedQuery
from app.application.queries.get_products import (
    GetProductsQuery,
    GetProductByIdQuery,
)
from app.application.queries.get_order import (
    GetOrderByIdQuery,
    GetUserOrdersQuery,
)

__all__ = [
    "Query",
    "CachedQuery",
    "GetProductsQuery",
    "GetProductByIdQuery",
    "GetOrderByIdQuery",
    "GetUserOrdersQuery",
]