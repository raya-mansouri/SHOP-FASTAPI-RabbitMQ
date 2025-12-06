"""
Unit tests for domain exceptions.

Tests exception creation, serialization, and error codes.
"""
import pytest
from uuid import uuid4

from app.domain.exceptions import (
    InsufficientStockError,
    ProductNotFoundError,
    OrderNotFoundError,
    OrderAlreadyPaidError,
    OrderNotPendingError,
    InvalidStatusTransitionError,
    OptimisticLockError,
    DuplicatePaymentError,
)


class TestInsufficientStockError:
    """Test InsufficientStockError exception."""
    
    def test_creates_with_all_fields(self):
        """Should create exception with all required fields."""
        error = InsufficientStockError(
            product_id=1,
            product_name="Test Product",
            requested=10,
            available=5
        )
        
        assert error.product_id == 1
        assert error.requested == 10
        assert error.available == 5
        assert "Test Product" in error.message
        assert "10" in error.message
        assert "5" in error.message
    
    def test_to_dict_includes_details(self):
        """Should serialize to dict with all details."""
        error = InsufficientStockError(
            product_id=1,
            product_name="Test Product",
            requested=10,
            available=5
        )
        
        result = error.to_dict()
        
        assert result["error"] == "BUSINESS_RULE_VIOLATION"
        assert result["details"]["product_id"] == 1
        assert result["details"]["requested"] == 10
        assert result["details"]["available"] == 5


class TestProductNotFoundError:
    """Test ProductNotFoundError exception."""
    
    def test_creates_with_product_id(self):
        """Should create exception with product ID."""
        error = ProductNotFoundError(product_id=123)
        
        assert "123" in error.message
        assert error.code == "NOT_FOUND"
    
    def test_to_dict_includes_entity_info(self):
        """Should include entity type and ID in dict."""
        error = ProductNotFoundError(product_id=123)
        result = error.to_dict()
        
        assert result["error"] == "NOT_FOUND"
        assert result["details"]["entity_type"] == "Product"
        assert result["details"]["entity_id"] == "123"


class TestOrderNotFoundError:
    """Test OrderNotFoundError exception."""
    
    def test_creates_with_order_id(self):
        """Should create exception with order ID."""
        order_id = str(uuid4())
        error = OrderNotFoundError(order_id=order_id)
        
        assert order_id in error.message
        assert error.code == "NOT_FOUND"


class TestOrderAlreadyPaidError:
    """Test OrderAlreadyPaidError exception."""
    
    def test_creates_with_order_id(self):
        """Should create exception with order ID."""
        order_id = str(uuid4())
        error = OrderAlreadyPaidError(order_id=order_id)
        
        assert order_id in error.message
        assert error.code == "BUSINESS_RULE_VIOLATION"
        assert "already been paid" in error.message


class TestOrderNotPendingError:
    """Test OrderNotPendingError exception."""
    
    def test_creates_with_status(self):
        """Should create exception with current status."""
        order_id = str(uuid4())
        error = OrderNotPendingError(order_id=order_id, current_status="PAID")
        
        assert order_id in error.message
        assert "PAID" in error.message
        assert error.code == "BUSINESS_RULE_VIOLATION"


class TestInvalidStatusTransitionError:
    """Test InvalidStatusTransitionError exception."""
    
    def test_creates_with_transition_info(self):
        """Should create exception with transition details."""
        order_id = str(uuid4())
        error = InvalidStatusTransitionError(
            order_id=order_id,
            from_status="PAID",
            to_status="PENDING"
        )
        
        assert order_id in error.message
        assert "PAID" in error.message
        assert "PENDING" in error.message
        
        result = error.to_dict()
        assert result["details"]["from_status"] == "PAID"
        assert result["details"]["to_status"] == "PENDING"


class TestOptimisticLockError:
    """Test OptimisticLockError exception."""
    
    def test_creates_with_entity_info(self):
        """Should create exception with entity type and ID."""
        error = OptimisticLockError(entity_type="Product", entity_id=123)
        
        assert "Product" in error.message
        assert "123" in error.message
        assert error.code == "CONCURRENCY_ERROR"


class TestDuplicatePaymentError:
    """Test DuplicatePaymentError exception."""
    
    def test_creates_with_idempotency_key(self):
        """Should create exception with idempotency key."""
        order_id = str(uuid4())
        error = DuplicatePaymentError(
            idempotency_key="test-key-123",
            existing_order_id=order_id
        )
        
        assert "test-key-123" in error.message
        assert error.code == "DUPLICATE_PAYMENT"
        
        result = error.to_dict()
        assert result["details"]["idempotency_key"] == "test-key-123"
        assert result["details"]["existing_order_id"] == order_id
