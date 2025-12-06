"""
Repository integration tests.

These tests use a real database to verify repository behavior.
"""

import pytest

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.infrastructure.database.models import (
    ProductModel,
    OrderModel,
    OrderItemModel,
    OrderStatus,
    BaseModel,
    Base
)
from app.infrastructure.database.repositories import (
    ProductRepository,
    OrderRepository,
)


# Test database URL - use separate test database!
TEST_DATABASE_URL = "postgresql+asyncpg://orderuser:orderpass@localhost:5432/orders_db"


@pytest.fixture(scope="function")
async def engine():
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Clean up
    await engine.dispose()


@pytest.fixture
async def session(engine):
    """Create test session with transaction rollback."""
    async with engine.connect() as connection:
        async with connection.begin() as transaction:
            async_session = async_sessionmaker(
                bind=connection,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            async with async_session() as session:
                yield session
                
                # Rollback happens automatically when exiting the context


@pytest.fixture
async def product_repo(session):
    """Create product repository."""
    return ProductRepository(session)


@pytest.fixture
async def order_repo(session):
    """Create order repository."""
    return OrderRepository(session)


@pytest.fixture
async def sample_product(session) -> ProductModel:
    """Create a sample product."""
    product = ProductModel(
        name="Test Product",
        price=9000,
        stock=100,
    )
    session.add(product)
    await session.flush()
    return product


class TestProductRepository:
    """Tests for ProductRepository."""
    
    async def test_get_by_id_returns_product(
        self, 
        product_repo: ProductRepository,
        sample_product: ProductModel
    ):
        """Should return product when exists."""
        result = await product_repo.get_by_id(sample_product.id)
        
        assert result is not None
        assert result.id == sample_product.id
        assert result.name == "Test Product"
    
    async def test_get_by_id_returns_none_when_not_found(
        self, 
        product_repo: ProductRepository
    ):
        """Should return None when product doesn't exist."""
        result = await product_repo.get_by_id(99999)
        assert result is None
    
    async def test_get_by_ids_returns_multiple_products(
        self,
        session: AsyncSession,
        product_repo: ProductRepository
    ):
        """Should return all requested products."""
        # Create multiple products
        products = [
            ProductModel(name=f"Product {i}", price=99000, stock=10)
            for i in range(3)
        ]
        session.add_all(products)
        await session.flush()
        
        ids = [p.id for p in products]
        result = await product_repo.get_by_ids(ids)
        
        assert len(result) == 3
    
    async def test_update_stock_succeeds_with_correct_version(
        self,
        product_repo: ProductRepository,
        sample_product: ProductModel
    ):
        """Should update stock when version matches."""
        success = await product_repo.update_stock(
            product_id=sample_product.id,
            quantity_delta=-10,
            expected_version=sample_product.version
        )
        
        assert success is True
    
    async def test_update_stock_fails_with_wrong_version(
        self,
        product_repo: ProductRepository,
        sample_product: ProductModel
    ):
        """Should fail when version doesn't match."""
        success = await product_repo.update_stock(
            product_id=sample_product.id,
            quantity_delta=-10,
            expected_version=999  # Wrong version
        )
        
        assert success is False
    
    async def test_update_stock_fails_when_would_go_negative(
        self,
        product_repo: ProductRepository,
        sample_product: ProductModel
    ):
        """Should fail when stock would go negative."""
        success = await product_repo.update_stock(
            product_id=sample_product.id,
            quantity_delta=-200,  # More than available (100)
            expected_version=sample_product.version
        )
        
        assert success is False


class TestOrderRepository:
    """Tests for OrderRepository."""
    
    async def test_create_order_with_items(
        self,
        order_repo: OrderRepository,
        sample_product: ProductModel
    ):
        """Should create order with items."""
        order = OrderModel(
            user_id=1,
            status=OrderStatus.PENDING,
            total_price=99000,
        )
        order.items = [
            OrderItemModel(
                product_id=sample_product.id,
                quantity=1,
                unit_price=sample_product.price,
            )
        ]
        
        created = await order_repo.create(order)
        
        assert created.id is not None
        assert len(created.items) == 1
        assert created.items[0].product_id == sample_product.id
    
    async def test_get_by_id_loads_items(
        self,
        order_repo: OrderRepository,
        sample_product: ProductModel
    ):
        """Should eagerly load order items."""
        # Create order
        order = OrderModel(user_id=1, total_price=9000)
        order.items = [
            OrderItemModel(
                product_id=sample_product.id,
                quantity=2,
                unit_price=sample_product.price,
            )
        ]
        created = await order_repo.create(order)
        
        # Fetch it
        fetched = await order_repo.get_by_id(created.id)
        
        assert fetched is not None
        assert len(fetched.items) == 1
        assert fetched.items[0].quantity == 2
    
    async def test_update_status_with_optimistic_lock(
        self,
        order_repo: OrderRepository,
        sample_product: ProductModel
    ):
        """Should update status when version matches."""
        order = OrderModel(user_id=1, total_price=0)
        created = await order_repo.create(order)
        
        success = await order_repo.update_status(
            order_id=created.id,
            new_status=OrderStatus.PAID,
            expected_version=created.version
        )
        
        assert success is True
    
    async def test_update_status_fails_with_wrong_version(
        self,
        order_repo: OrderRepository,
        sample_product: ProductModel
    ):
        """Should fail when version doesn't match."""
        order = OrderModel(user_id=1, total_price=0)
        created = await order_repo.create(order)
        
        success = await order_repo.update_status(
            order_id=created.id,
            new_status=OrderStatus.PAID,
            expected_version=999  # Wrong version
        )
        
        assert success is False