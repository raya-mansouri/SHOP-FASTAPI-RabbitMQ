# app/main.py
"""
FastAPI Application Entry Point.

ARCHITECTURE:
- Lifespan management for connections
- Dependency injection setup
- Route registration
- Exception handlers
"""
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.infrastructure.database.session import sessionmanager
from app.infrastructure.cache.redis_client import redis_manager
from app.infrastructure.messaging.publisher import rabbitmq_publisher
from app.domain.exceptions import (
    DomainException,
    EntityNotFoundError,
    ValidationError,
    BusinessRuleViolation,
    ConcurrencyError,
)
from app.api.routes import products, orders, health

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown of:
    - Database connections
    - Redis connections
    - RabbitMQ connections
    """
    # Startup
    logger.info("Starting up application...")
    
    try:
        # Initialize Redis
        await redis_manager.connect()
        logger.info("Redis connected")
        
        # Initialize RabbitMQ
        await rabbitmq_publisher.connect()
        logger.info("RabbitMQ connected")
        
        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    
    try:
        await rabbitmq_publisher.disconnect()
        await redis_manager.disconnect()
        await sessionmanager.close()
        logger.info("Application shutdown complete")
    except Exception as e:
        logger.error(f"Shutdown error: {e}")


def create_app() -> FastAPI:
    """Application factory."""
    
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register exception handlers
    register_exception_handlers(app)
    
    # Register routes
    app.include_router(health.router, tags=["Health"])
    app.include_router(products.router, prefix="/products", tags=["Products"])
    app.include_router(orders.router, prefix="/orders", tags=["Orders"])
    
    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers."""
    
    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(
        request: Request,
        exc: EntityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=exc.to_dict(),
        )
    
    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request,
        exc: ValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=exc.to_dict(),
        )
    
    @app.exception_handler(BusinessRuleViolation)
    async def business_rule_handler(
        request: Request,
        exc: BusinessRuleViolation
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=exc.to_dict(),
        )
    
    @app.exception_handler(ConcurrencyError)
    async def concurrency_error_handler(
        request: Request,
        exc: ConcurrencyError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=exc.to_dict(),
        )
    
    @app.exception_handler(DomainException)
    async def domain_exception_handler(
        request: Request,
        exc: DomainException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=exc.to_dict(),
        )


# Create app instance
app = create_app()