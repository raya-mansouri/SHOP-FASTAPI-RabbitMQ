"""
Unit tests for cache key generation.

Tests that cache keys are generated correctly and consistently.
"""
import pytest
from uuid import uuid4

from app.infrastructure.cache.cache_service import CacheKeys


class TestCacheKeys:
    """Test CacheKeys utility class."""
    
    def test_product_key(self):
        """Should generate product cache key."""
        key = CacheKeys.product(123)
        assert key == "product:123"
        assert isinstance(key, str)
    
    def test_product_stock_key(self):
        """Should generate product stock cache key."""
        key = CacheKeys.product_stock(123)
        assert key == "product:123:stock"
    
    def test_order_key(self):
        """Should generate order cache key."""
        order_id = str(uuid4())
        key = CacheKeys.order(order_id)
        assert key == f"order:{order_id}"
    
    def test_user_orders_key(self):
        """Should generate user orders cache key."""
        key = CacheKeys.user_orders(user_id=42, skip=0, limit=20)
        assert key == "user:42:orders:0:20"
    
    def test_user_orders_pattern(self):
        """Should generate user orders pattern for deletion."""
        pattern = CacheKeys.user_orders_pattern(42)
        assert pattern == "user:42:orders:*"
    
    def test_product_list_key(self):
        """Should generate product list cache key."""
        key = CacheKeys.product_list(skip=0, limit=100)
        assert key == "product:list:0:100"
    
    def test_all_products_pattern(self):
        """Should generate all products pattern for deletion."""
        pattern = CacheKeys.all_products_pattern()
        assert pattern == "product:*"
    
    def test_lock_payment_key(self):
        """Should generate payment lock key."""
        order_id = str(uuid4())
        key = CacheKeys.lock_payment(order_id)
        assert key == f"lock:payment:{order_id}"
    
    def test_idempotency_key(self):
        """Should generate idempotency cache key."""
        key = CacheKeys.idempotency("test-key-123")
        assert key == "idempotency:test-key-123"
    
    def test_keys_are_consistent(self):
        """Should generate same key for same input."""
        key1 = CacheKeys.product(123)
        key2 = CacheKeys.product(123)
        assert key1 == key2
    
    def test_different_inputs_different_keys(self):
        """Should generate different keys for different inputs."""
        key1 = CacheKeys.product(123)
        key2 = CacheKeys.product(456)
        assert key1 != key2
