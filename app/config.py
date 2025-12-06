"""
Application configuration management.

DECISION: Using Pydantic Settings for configuration
WHY: Type-safe, automatic environment variable loading, validation
ALTERNATIVE: python-dotenv with os.environ - less type safety, no validation
ALTERNATIVE: dynaconf - more features but heavier dependency
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra env vars
    )
    
    # Application
    app_name: str = "Order Processing System"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    api_v1_prefix: str = "/api/v1"
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    log_level: str = "INFO"

    # Database
    database_url: Optional[str] = None  # Full URL (Docker)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "orders_db"
    
    # Connection Pool Settings
    # DECISION: Conservative pool sizes for stability
    # WHY: Prevents connection exhaustion under load
    db_pool_size: int = 5          # Base connections
    db_max_overflow: int = 10      # Extra connections when needed
    db_pool_timeout: int = 30      # Wait time for connection
    db_pool_recycle: int = 1800    # Recycle connections every 30 min
    db_echo: bool = False          # SQL logging (enable in dev)
    
    # Redis
    redis_url: Optional[str] = None  # Full URL (Docker)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    cache_ttl_idempotency: int = 86400  # 24 hours
    
    # RabbitMQ
    rabbitmq_url: Optional[str] = None  # Full URL (Docker)
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_vhost: str = "/"
    rabbitmq_queue_name: str = "order_processing"
    rabbitmq_exchange_name: str = "orders"
    rabbitmq_routing_key: str = "order.payment"
    rabbitmq_prefetch_count: int = 5
    rabbitmq_max_retries: int = 5
    
    def get_database_url(self) -> str:
        """
        Get async database URL.
        
        Supports both:
        1. Full URL from DATABASE_URL env var (Docker)
        2. Constructed from individual components (local dev)
        
        DECISION: Using asyncpg driver
        WHY: Best performance for async PostgreSQL
        ALTERNATIVE: psycopg3 (async) - newer but less mature async support
        """
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    @property
    def database_url_sync(self) -> str:
        """
        Sync database URL for Alembic migrations.
        
        DECISION: Separate sync URL for migrations
        WHY: Alembic doesn't fully support async operations
        """
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
    
    def get_redis_url(self) -> str:
        """
        Get Redis URL.
        
        Supports both:
        1. Full URL from REDIS_URL env var (Docker)
        2. Constructed from individual components (local dev)
        """
        if self.redis_url:
            return self.redis_url
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    def get_rabbitmq_url(self) -> str:
        """
        Get RabbitMQ URL.
        
        Supports both:
        1. Full URL from RABBITMQ_URL env var (Docker)
        2. Constructed from individual components (local dev)
        """
        if self.rabbitmq_url:
            return self.rabbitmq_url
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )
    
    @field_validator("db_pool_size")
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        """Ensure pool size is reasonable."""
        if v < 1 or v > 100:
            raise ValueError("Pool size must be between 1 and 100")
        return v


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    DECISION: Using lru_cache for singleton pattern
    WHY: Settings should be loaded once and reused
    ALTERNATIVE: Global variable - works but less clean
    """
    return Settings()


# Convenience export
settings = get_settings()