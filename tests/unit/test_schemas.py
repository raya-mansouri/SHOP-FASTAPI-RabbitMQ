"""
Unit tests for API schemas (Pydantic models).

Tests validation, serialization, and business rules.
"""
import pytest
from pydantic import ValidationError
from uuid import uuid4
from datetime import datetime

from app.api.schemas import (
    OrderCreate,
    OrderItemCreate,
    ProductCreate,
    PaymentRequest,
)


class TestOrderItemCreate:
    """Test OrderItemCreate schema validation."""
    
    def test_valid_order_item(self):
        """Should accept valid order item."""
        item = OrderItemCreate(product_id=1, quantity=5)
        assert item.product_id == 1
        assert item.quantity == 5
    
    def test_rejects_zero_quantity(self):
        """Should reject zero quantity."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(product_id=1, quantity=0)
        
        errors = exc_info.value.errors()
        assert any("quantity" in str(e) for e in errors)
    
    def test_rejects_negative_quantity(self):
        """Should reject negative quantity."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(product_id=1, quantity=-5)
        
        errors = exc_info.value.errors()
        assert any("quantity" in str(e) for e in errors)
    
    def test_rejects_excessive_quantity(self):
        """Should reject quantity over 100."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(product_id=1, quantity=101)
        
        errors = exc_info.value.errors()
        assert any("quantity" in str(e) for e in errors)
    
    def test_rejects_zero_product_id(self):
        """Should reject zero product ID."""
        with pytest.raises(ValidationError) as exc_info:
            OrderItemCreate(product_id=0, quantity=5)
        
        errors = exc_info.value.errors()
        assert any("product_id" in str(e) for e in errors)


class TestOrderCreate:
    """Test OrderCreate schema validation."""
    
    def test_valid_order(self):
        """Should accept valid order."""
        order = OrderCreate(
            user_id=1,
            items=[
                OrderItemCreate(product_id=1, quantity=2),
                OrderItemCreate(product_id=2, quantity=3),
            ]
        )
        assert order.user_id == 1
        assert len(order.items) == 2
    
    def test_rejects_empty_items(self):
        """Should reject order with no items."""
        with pytest.raises(ValidationError) as exc_info:
            OrderCreate(user_id=1, items=[])
        
        errors = exc_info.value.errors()
        assert any("items" in str(e) for e in errors)
    
    def test_rejects_duplicate_products(self):
        """Should reject order with duplicate product IDs."""
        with pytest.raises(ValidationError) as exc_info:
            OrderCreate(
                user_id=1,
                items=[
                    OrderItemCreate(product_id=1, quantity=2),
                    OrderItemCreate(product_id=1, quantity=3),
                ]
            )
        
        assert "Duplicate product IDs" in str(exc_info.value)
    
    def test_rejects_too_many_items(self):
        """Should reject order with more than 50 items."""
        items = [OrderItemCreate(product_id=i+1, quantity=1) for i in range(51)]
        
        with pytest.raises(ValidationError) as exc_info:
            OrderCreate(user_id=1, items=items)
        
        errors = exc_info.value.errors()
        assert any("items" in str(e) for e in errors)
    
    def test_rejects_zero_user_id(self):
        """Should reject zero user ID."""
        with pytest.raises(ValidationError) as exc_info:
            OrderCreate(
                user_id=0,
                items=[OrderItemCreate(product_id=1, quantity=1)]
            )
        
        errors = exc_info.value.errors()
        assert any("user_id" in str(e) for e in errors)


class TestProductCreate:
    """Test ProductCreate schema validation."""
    
    def test_valid_product(self):
        """Should accept valid product."""
        product = ProductCreate(name="Test Product", price=1000, stock=50)
        assert product.name == "Test Product"
        assert product.price == 1000
        assert product.stock == 50
    
    def test_rejects_empty_name(self):
        """Should reject empty product name."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(name="", price=1000, stock=50)
        
        errors = exc_info.value.errors()
        assert any("name" in str(e) for e in errors)
    
    def test_rejects_zero_price(self):
        """Should reject zero price."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(name="Test", price=0, stock=50)
        
        errors = exc_info.value.errors()
        assert any("price" in str(e) for e in errors)
    
    def test_rejects_negative_price(self):
        """Should reject negative price."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(name="Test", price=-100, stock=50)
        
        errors = exc_info.value.errors()
        assert any("price" in str(e) for e in errors)
    
    def test_rejects_negative_stock(self):
        """Should reject negative stock."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(name="Test", price=1000, stock=-5)
        
        errors = exc_info.value.errors()
        assert any("stock" in str(e) for e in errors)
    
    def test_accepts_zero_stock(self):
        """Should accept zero stock (out of stock product)."""
        product = ProductCreate(name="Test", price=1000, stock=0)
        assert product.stock == 0


class TestPaymentRequest:
    """Test PaymentRequest schema validation."""
    
    def test_valid_with_idempotency_key(self):
        """Should accept valid payment request with idempotency key."""
        request = PaymentRequest(idempotency_key="test-key-123")
        assert request.idempotency_key == "test-key-123"
    
    def test_valid_without_idempotency_key(self):
        """Should accept payment request without idempotency key."""
        request = PaymentRequest()
        assert request.idempotency_key is None
    
    def test_rejects_empty_idempotency_key(self):
        """Should reject empty idempotency key."""
        with pytest.raises(ValidationError) as exc_info:
            PaymentRequest(idempotency_key="")
        
        errors = exc_info.value.errors()
        assert any("idempotency_key" in str(e) for e in errors)
    
    def test_rejects_too_long_idempotency_key(self):
        """Should reject idempotency key longer than 255 characters."""
        long_key = "x" * 256
        
        with pytest.raises(ValidationError) as exc_info:
            PaymentRequest(idempotency_key=long_key)
        
        errors = exc_info.value.errors()
        assert any("idempotency_key" in str(e) for e in errors)
