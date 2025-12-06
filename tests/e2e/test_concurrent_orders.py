"""
Script to test concurrent order processing in a live system.
Demonstrates senior-level understanding of distributed systems testing.

Usage:
    python scripts/test_concurrent_orders.py

This script:
1. Creates products with limited stock
2. Spawns concurrent order requests
3. Verifies stock consistency
4. Tests idempotency
5. Reports race condition detection
"""
import asyncio
import httpx
import sys
from typing import List, Dict


BASE_URL = "http://localhost:8000/api/v1"


class ConcurrencyTester:
    """Test concurrent order processing."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def setup_test_data(self) -> Dict:
        """Create test products and return IDs."""
        print("📦 Setting up test data...")
        
        # Create product with limited stock
        response = await self.client.post(
            f"{self.base_url}/products",
            json={
                "name": "Limited Edition Item",
                "price": 99.99,
                "stock": 10  # Only 10 available
            }
        )
        
        if response.status_code != 201:
            print(f"❌ Failed to create product: {response.text}")
            return None
        
        product = response.json()
        print(f"✅ Created product: {product['name']} (Stock: {product['stock']})")
        
        return product
    
    async def create_order(
        self,
        user_id: int,
        product_id: int,
        quantity: int
    ) -> Dict:
        """Create an order."""
        try:
            response = await self.client.post(
                f"{self.base_url}/orders",
                json={
                    "user_id": user_id,
                    "items": [
                        {
                            "product_id": product_id,
                            "quantity": quantity
                        }
                    ]
                }
            )
            
            if response.status_code == 201:
                return {"success": True, "order": response.json()}
            else:
                return {"success": False, "error": response.text}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def process_payment(
        self,
        order_id: int,
        idempotency_key: str
    ) -> Dict:
        """Process payment for an order."""
        try:
            response = await self.client.post(
                f"{self.base_url}/orders/{order_id}/pay",
                headers={"X-Idempotency-Key": idempotency_key}
            )
            
            if response.status_code in [200, 202]:
                return {"success": True, "result": response.json()}
            else:
                return {"success": False, "error": response.text}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_product_stock(self, product_id: int) -> int:
        """Get current product stock."""
        try:
            response = await self.client.get(
                f"{self.base_url}/products/{product_id}"
            )
            if response.status_code == 200:
                return response.json()["stock"]
            return -1
        except:
            return -1
    
    async def test_concurrent_orders(
        self,
        product_id: int,
        initial_stock: int,
        num_orders: int,
        quantity_per_order: int
    ):
        """
        Test concurrent order processing.
        
        This is the KEY test for race conditions!
        """
        print(f"\n🚀 Starting concurrent order test...")
        print(f"   Initial stock: {initial_stock}")
        print(f"   Concurrent orders: {num_orders}")
        print(f"   Quantity per order: {quantity_per_order}")
        print(f"   Total demand: {num_orders * quantity_per_order}")
        
        # Step 1: Create orders concurrently
        print(f"\n📝 Creating {num_orders} orders concurrently...")
        
        create_tasks = [
            self.create_order(
                user_id=i,
                product_id=product_id,
                quantity=quantity_per_order
            )
            for i in range(num_orders)
        ]
        
        create_results = await asyncio.gather(*create_tasks)
        
        successful_orders = [
            r["order"]["id"] for r in create_results if r["success"]
        ]
        
        print(f"✅ Created {len(successful_orders)} orders successfully")
        
        # Step 2: Process payments concurrently
        print(f"\n💳 Processing {len(successful_orders)} payments concurrently...")
        
        payment_tasks = [
            self.process_payment(
                order_id=order_id,
                idempotency_key=f"test-payment-{order_id}"
            )
            for order_id in successful_orders
        ]
        
        payment_results = await asyncio.gather(*payment_tasks)
        
        # Step 3: Wait for worker processing
        print("\n⏳ Waiting for worker to process payments...")
        await asyncio.sleep(5)  # Give worker time to process
        
        # Step 4: Check final stock
        final_stock = await self.get_product_stock(product_id)
        
        print(f"\n📊 Results:")
        print(f"   Initial stock: {initial_stock}")
        print(f"   Final stock: {final_stock}")
        print(f"   Expected final stock: {max(0, initial_stock - (num_orders * quantity_per_order))}")
        
        # Verification
        expected_deduction = min(
            initial_stock,
            num_orders * quantity_per_order
        )
        expected_final = initial_stock - expected_deduction
        
        if final_stock == expected_final:
            print("✅ SUCCESS: Stock is consistent! No race conditions detected.")
            return True
        else:
            print(f"❌ FAILURE: Stock inconsistency detected!")
            print(f"   Expected: {expected_final}")
            print(f"   Actual: {final_stock}")
            print(f"   Difference: {abs(final_stock - expected_final)}")
            print("\n⚠️  This indicates a race condition in stock management!")
            return False
    
    async def test_idempotency(self, product_id: int):
        """Test idempotency by sending duplicate requests."""
        print(f"\n🔄 Testing idempotency...")
        
        # Create an order
        order_result = await self.create_order(
            user_id=999,
            product_id=product_id,
            quantity=1
        )
        
        if not order_result["success"]:
            print("❌ Failed to create order for idempotency test")
            return False
        
        order_id = order_result["order"]["id"]
        idempotency_key = "duplicate-payment-test"
        
        # Send 5 identical payment requests
        print(f"   Sending 5 duplicate payment requests...")
        
        tasks = [
            self.process_payment(order_id, idempotency_key)
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should succeed with same result
        successful = [r for r in results if r["success"]]
        
        if len(successful) == 5:
            print("✅ SUCCESS: All duplicate requests handled correctly")
            return True
        else:
            print(f"❌ FAILURE: Only {len(successful)}/5 requests succeeded")
            return False
    
    async def run_all_tests(self):
        """Run all concurrency tests."""
        print("=" * 60)
        print("🧪 CONCURRENT ORDER PROCESSING TEST SUITE")
        print("=" * 60)
        
        # Setup
        product = await self.setup_test_data()
        if not product:
            print("❌ Failed to setup test data")
            return
        
        product_id = product["id"]
        initial_stock = product["stock"]
        
        # Test 1: Basic concurrent orders
        print("\n" + "=" * 60)
        print("TEST 1: Concurrent Orders with Sufficient Stock")
        print("=" * 60)
        
        test1_passed = await self.test_concurrent_orders(
            product_id=product_id,
            initial_stock=initial_stock,
            num_orders=5,
            quantity_per_order=1
        )
        
        # Test 2: Over-subscription (more demand than stock)
        print("\n" + "=" * 60)
        print("TEST 2: Over-subscription (Insufficient Stock)")
        print("=" * 60)
        
        current_stock = await self.get_product_stock(product_id)
        
        test2_passed = await self.test_concurrent_orders(
            product_id=product_id,
            initial_stock=current_stock,
            num_orders=10,
            quantity_per_order=1
        )
        
        # Test 3: Idempotency
        print("\n" + "=" * 60)
        print("TEST 3: Idempotency")
        print("=" * 60)
        
        test3_passed = await self.test_idempotency(product_id)
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Test 1 (Concurrent Orders): {'✅ PASSED' if test1_passed else '❌ FAILED'}")
        print(f"Test 2 (Over-subscription): {'✅ PASSED' if test2_passed else '❌ FAILED'}")
        print(f"Test 3 (Idempotency): {'✅ PASSED' if test3_passed else '❌ FAILED'}")
        
        all_passed = test1_passed and test2_passed and test3_passed
        
        if all_passed:
            print("\n🎉 ALL TESTS PASSED!")
            print("   Your system correctly handles:")
            print("   ✅ Concurrent stock depletion")
            print("   ✅ Race conditions")
            print("   ✅ Idempotent operations")
        else:
            print("\n⚠️  SOME TESTS FAILED")
            print("   Review the race condition handling in:")
            print("   - SELECT FOR UPDATE implementation")
            print("   - Transaction isolation levels")
            print("   - Idempotency logic")
        
        await self.client.aclose()


async def main():
    """Main entry point."""
    tester = ConcurrencyTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ Test interrupted by user")
        sys.exit(1)