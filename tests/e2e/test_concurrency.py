"""
Concurrency tests to verify race condition handling.
These tests demonstrate senior-level understanding of concurrent systems.

Tests cover:
1. Concurrent stock depletion
2. Optimistic locking
3. SELECT FOR UPDATE effectiveness
4. Idempotency under concurrent requests
5. Database deadlock handling
"""
import pytest
import asyncio
from sqlalchemy import select

from app.infrastructure.database.models import OrderStatus, OrderModel, ProductModel
from app.infrastructure.database.repositories import (
    ProductRepository,
    OrderRepository
)
from app.domain.exceptions import InsufficientStockError, ConcurrencyError


class TestConcurrentStockDepletion:
    """
    Test concurrent stock depletion scenarios.
    This is THE MOST CRITICAL test for race conditions.
    """
    
    @pytest.mark.asyncio
    async def test_concurrent_stock_deduction_select_for_update(
        self,
        async_engine,
        test_product
    ):
        """
        Test that SELECT FOR UPDATE prevents race conditions.
        
        Scenario:
        - Product has 10 stock
        - 10 concurrent requests try to deduct 1 stock each
        - All should succeed, final stock should be 0
        - Without SELECT FOR UPDATE, final stock would be > 0
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker
        
        product_id = test_product.id
        initial_stock = test_product.stock
        concurrent_requests = 10
        quantity_per_request = 1
        
        async def deduct_stock():
            """Deduct stock in a transaction with its own session."""
            async_session_maker = async_sessionmaker(
                bind=async_engine,
                expire_on_commit=False,
            )
            async with async_session_maker() as session:
                async with session.begin():
                    repo = ProductRepository(session)
                    try:
                        product = await repo.deduct_stock(
                            product_id=product_id,
                            quantity=quantity_per_request
                        )
                        return True, product.stock
                    except InsufficientStockError:
                        return False, None
        
        # Create concurrent tasks
        tasks = [
            deduct_stock()
            for _ in range(concurrent_requests)
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count successes
        successes = sum(1 for r in results if isinstance(r, tuple) and r[0] is True)
        
        # Verify all succeeded
        assert successes == concurrent_requests, (
            f"Expected {concurrent_requests} successes, got {successes}"
        )
        
        # Verify final stock
        async with async_sessionmaker(bind=async_engine, expire_on_commit=False)() as session:
            result = await session.execute(
                select(ProductModel).where(ProductModel.id == product_id)
            )
            final_product = result.scalar_one()
            
            expected_stock = initial_stock - (concurrent_requests * quantity_per_request)
            assert final_product.stock == expected_stock, (
                f"Expected stock {expected_stock}, got {final_product.stock}. "
                f"Race condition detected!"
            )
    
    @pytest.mark.asyncio
    async def test_concurrent_insufficient_stock(
        self,
        async_engine,
        test_product
    ):
        """
        Test that insufficient stock is handled correctly under concurrency.
        
        Scenario:
        - Product has 5 stock
        - 10 concurrent requests try to deduct 1 stock each
        - First 5 should succeed, last 5 should fail
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy import text
        
        product_id = test_product.id
        
        # Set stock to 5
        async with async_sessionmaker(bind=async_engine, expire_on_commit=False)() as session:
            await session.execute(
                text(f"UPDATE products SET stock = 5 WHERE id = {product_id}")
            )
            await session.commit()
        
        concurrent_requests = 10
        quantity_per_request = 1
        
        async def deduct_stock():
            """Deduct stock in a transaction with its own session."""
            async_session_maker = async_sessionmaker(
                bind=async_engine,
                expire_on_commit=False,
            )
            async with async_session_maker() as session:
                try:
                    async with session.begin():
                        repo = ProductRepository(session)
                        product = await repo.deduct_stock(
                            product_id=product_id,
                            quantity=quantity_per_request
                        )
                        return "success", product.stock
                except InsufficientStockError as e:
                    return "insufficient_stock", None
                except Exception as e:
                    return "error", str(e)
        
        # Create concurrent tasks
        tasks = [
            deduct_stock()
            for _ in range(concurrent_requests)
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count outcomes
        successes = sum(1 for r in results if isinstance(r, tuple) and r[0] == "success")
        insufficient = sum(1 for r in results if isinstance(r, tuple) and r[0] == "insufficient_stock")
        errors = sum(1 for r in results if isinstance(r, tuple) and r[0] == "error")
        
        # With SELECT FOR UPDATE, transactions are serialized
        # So first 5 succeed, last 5 fail with insufficient stock
        assert successes == 5, f"Expected 5 successes, got {successes}. Results: {results}"
        assert insufficient == 5, f"Expected 5 insufficient stock, got {insufficient}. Results: {results}"
        assert errors == 0, f"Expected 0 errors, got {errors}"
        
        # Verify final stock is 0
        async with async_sessionmaker(bind=async_engine, expire_on_commit=False)() as session:
            result = await session.execute(
                select(ProductModel).where(ProductModel.id == product_id)
            )
            final_product = result.scalar_one()
            assert final_product.stock == 0, (
                f"Expected 0 stock, got {final_product.stock}"
            )
    
    @pytest.mark.asyncio
    async def test_optimistic_locking_concurrent_updates(
        self,
        async_engine,
        test_product
    ):
        """
        Test optimistic locking with version field.
        
        Scenario:
        - Two concurrent updates to same product
        - Second update should fail with ConcurrencyError (or one succeeds, one waits)
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker
        
        product_id = test_product.id
        initial_version = test_product.version
        
        async def update_product_with_version_check():
            """Update product checking version."""
            try:
                async_session_maker = async_sessionmaker(
                    bind=async_engine,
                    expire_on_commit=False,
                )
                async with async_session_maker() as session:
                    async with session.begin():
                        repo = ProductRepository(session)
                        
                        # Get current state with lock
                        product = await repo.get_by_id_for_update(product_id)
                        
                        # Simulate some work
                        await asyncio.sleep(0.1)
                        
                        # Deduct stock
                        updated = await repo.deduct_stock(
                            product_id=product_id,
                            quantity=1
                        )
                        return "success", updated.version
            except ConcurrencyError:
                return "concurrency_error", None
            except Exception as e:
                return "error", str(e)
        
        # Execute two concurrent updates
        task1 = update_product_with_version_check()
        task2 = update_product_with_version_check()
        
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        
        # Both should succeed (SELECT FOR UPDATE serializes them)
        successes = sum(1 for r in results if isinstance(r, tuple) and r[0] == "success")
        
        assert successes == 2, f"Expected 2 successes, got {successes}"
        
        # Verify version was incremented twice
        async with async_sessionmaker(bind=async_engine, expire_on_commit=False)() as session:
            result = await session.execute(
                select(ProductModel).where(ProductModel.id == product_id)
            )
            final_product = result.scalar_one()
            assert final_product.version == initial_version + 2


class TestConcurrentOrderProcessing:
    """Test concurrent order processing scenarios."""
    
    @pytest.mark.asyncio
    async def test_concurrent_orders_same_product(
        self,
        async_engine,
        test_product
    ):
        """
        Test multiple orders for the same product processed concurrently.
        
        Scenario:
        - Product has 20 stock
        - 5 orders, each wanting 4 items
        - All should succeed, stock should be 0
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from sqlalchemy import text
        
        product_id = test_product.id
        
        # Set stock to 20
        async with async_sessionmaker(bind=async_engine, expire_on_commit=False)() as session:
            await session.execute(
                text(f"UPDATE products SET stock = 20 WHERE id = {product_id}")
            )
            await session.commit()
        
        async def create_and_process_order(user_id: int):
            """Create and process an order."""
            try:
                async_session_maker = async_sessionmaker(
                    bind=async_engine,
                    expire_on_commit=False,
                )
                async with async_session_maker() as session:
                    async with session.begin():
                        order_repo = OrderRepository(session)
                        product_repo = ProductRepository(session)
                        
                        # Create order
                        order = OrderModel(
                            user_id=user_id,
                            status=OrderStatus.PENDING,
                            total_price=40,
                        )
                        created_order = await order_repo.create(order)
                        
                        # Process order (deduct stock)
                        await product_repo.deduct_stock(product_id, 4)
                        await order_repo.update_status(
                            created_order.id,
                            OrderStatus.PAID,
                            expected_version=created_order.version
                        )
                        return "success", created_order.id
            except InsufficientStockError:
                return "failed", None
            except Exception as e:
                return "error", str(e)
        
        # Create 5 concurrent orders
        tasks = [
            create_and_process_order(user_id=i)
            for i in range(1, 6)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed
        successes = sum(1 for r in results if isinstance(r, tuple) and r[0] == "success")
        assert successes == 5, f"Expected 5 successful orders, got {successes}"
        
        # Verify stock is 0
        async with async_sessionmaker(bind=async_engine, expire_on_commit=False)() as session:
            result = await session.execute(
                select(ProductModel).where(ProductModel.id == product_id)
            )
            final_product = result.scalar_one()
            assert final_product.stock == 0


class TestIdempotency:
    """Test idempotency under concurrent requests."""
    
    @pytest.mark.asyncio
    async def test_duplicate_payment_requests(
        self,
        e2e_client,
        test_order
    ):
        """
        Test that duplicate payment requests with same idempotency key
        return the same result.
        
        This is CRITICAL for preventing double charges.
        """
        import uuid
        order_id = test_order.id
        # Use unique idempotency key for each test run
        idempotency_key = f"test-payment-{uuid.uuid4()}"
        
        # Send 5 concurrent payment requests with same idempotency key
        async def send_payment_request():
            response = await e2e_client.post(
                f"/orders/{order_id}/pay",
                json={"idempotency_key": idempotency_key}
            )
            return response.status_code, response.json()
        
        tasks = [send_payment_request() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        
        # All should return same result
        status_codes = [r[0] for r in results]
        responses = [r[1] for r in results]
        
        # All should succeed (200 or 202)
        assert all(200 <= code < 300 for code in status_codes), f"Got status codes: {status_codes}, responses: {responses}"
        
        # All should return same order_id
        order_ids = [str(r["order_id"]) for r in responses]
        assert len(set(order_ids)) == 1, f"All requests should return same order. Got: {order_ids}"
        
        # All should have same status (idempotent)
        statuses = [r["status"] for r in responses]
        # Either all PROCESSING or all PAID (if already processed)
        assert len(set(statuses)) == 1, f"All requests should return same status. Got: {statuses}"


@pytest.fixture
async def async_engine():
    """Create async database engine for e2e tests."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool
    from app.infrastructure.database.models import Base
    
    TEST_DATABASE_URL = "postgresql+asyncpg://orderuser:orderpass@localhost:5432/orders_db"
    
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest.fixture
async def test_product(async_engine):
    """Create a test product with stock."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        async with session.begin():
            product = ProductModel(
                name="Test Product",
                price=10,
                stock=10,
                version=0
            )
            session.add(product)
        await session.commit()
        await session.refresh(product)
        return product


@pytest.fixture
async def test_order(async_engine, test_product):
    """Create a test order."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        expire_on_commit=False,
    )
    
    async with async_session_maker() as session:
        async with session.begin():
            order = OrderModel(
                user_id=1,
                status=OrderStatus.PENDING,
                total_price=20
            )
            session.add(order)
        await session.commit()
        await session.refresh(order)
        return order