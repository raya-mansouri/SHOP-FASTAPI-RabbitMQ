# app/api/routes/health.py
"""
Health Check Routes.

ENDPOINTS:
- GET /health - Basic health check
- GET /health/ready - Readiness check (all dependencies)
"""
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.infrastructure.cache.redis_client import redis_manager
from app.infrastructure.messaging.publisher import rabbitmq_publisher

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - verifies all dependencies are available.
    
    Checks:
    - Redis connection
    - RabbitMQ connection
    """
    checks = {
        "redis": await redis_manager.health_check(),
        "rabbitmq": await rabbitmq_publisher.health_check(),
    }
    
    all_healthy = all(checks.values())
    
    if all_healthy:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ready",
                "checks": checks,
            },
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not ready",
                "checks": checks,
            },
        )
