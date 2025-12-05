"""
Cache Key Management.

DECISION: Centralized key management
WHY:
  - Consistent key naming
  - Easy to find all keys for an entity
  - Prevent key collisions
  - Simple cache invalidation

PATTERN: Entity:ID:Field or Entity:List:Filter
"""



class CacheKeys:
    """
    Cache key generator.
    
    NAMING CONVENTION:
    - Singular entity: {entity}:{id}
    - List: {entity}:list:{filter}
    - Lock: lock:{entity}:{id}
    
    DECISION: Using colons as separators
    WHY: Redis convention, works with SCAN patterns
    """
    
    # TTL values (in seconds)
    TTL_SHORT = 60          # 1 minute - volatile data
    TTL_MEDIUM = 300        # 5 minutes - product list
    TTL_LONG = 3600         # 1 hour - stable data
    TTL_IDEMPOTENCY = 86400 # 24 hours - idempotency keys
    
    # ========================================================================
    # PRODUCT KEYS
    # ========================================================================
    
    @staticmethod
    def product(product_id: int) -> str:
        """Single product cache key."""
        return f"product:{product_id}"
    
    @staticmethod
    def product_list(skip: int = 0, limit: int = 100) -> str:
        """Product list cache key."""
        return f"product:list:{skip}:{limit}"
    
    @staticmethod
    def all_products_pattern() -> str:
        """Pattern to match all product keys (for invalidation)."""
        return "product:*"
    
    @staticmethod
    def product_stock(product_id: int) -> str:
        """Product stock level key (frequently updated)."""
        return f"product:{product_id}:stock"
    
    # ========================================================================
    # ORDER KEYS
    # ========================================================================
    
    @staticmethod
    def order(order_id: str) -> str:
        """Single order cache key."""
        return f"order:{order_id}"
    
    @staticmethod
    def user_orders(user_id: int, skip: int = 0, limit: int = 20) -> str:
        """User orders list cache key."""
        return f"user:{user_id}:orders:{skip}:{limit}"
    
    @staticmethod
    def user_orders_pattern(user_id: int) -> str:
        """Pattern for all user order keys."""
        return f"user:{user_id}:orders:*"
    
    # ========================================================================
    # IDEMPOTENCY KEYS
    # ========================================================================
    
    @staticmethod
    def idempotency(key: str) -> str:
        """Idempotency key for payment deduplication."""
        return f"idempotency:{key}"
    
    # ========================================================================
    # LOCK KEYS
    # ========================================================================
    
    @staticmethod
    def lock_order(order_id: str) -> str:
        """Distributed lock for order processing."""
        return f"lock:order:{order_id}"
    
    @staticmethod
    def lock_payment(order_id: str) -> str:
        """Distributed lock for payment processing."""
        return f"lock:payment:{order_id}"