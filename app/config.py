"""
Application configuration management.

DECISION: Using Pydantic Settings for configuration
WHY: Type-safe, automatic environment variable loading, validation
ALTERNATIVE: python-dotenv with os.environ - less type safety, no validation
ALTERNATIVE: dynaconf - more features but heavier dependency
"""

from functools import lru_cache
from typing import Optional

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
    
    # Database
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
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    # RabbitMQ
    rabbitmq_host: str = "localhost"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_vhost: str = "/"
    
    @property
    def database_url(self) -> str:
        """
        Construct async database URL.
        
        DECISION: Using asyncpg driver
        WHY: Best performance for async PostgreSQL
        ALTERNATIVE: psycopg3 (async) - newer but less mature async support
        """
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
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def rabbitmq_url(self) -> str:
        """Construct RabbitMQ URL."""
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