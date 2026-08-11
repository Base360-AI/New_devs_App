import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import logging
import os
import time

from app.core.redis_client import redis_client
from .api.v1 import (
    users_lightning,
    cities,
    city_access_fast,
    city_access_fixed,
    departments,
    profile,
    company_settings,
    auth_info,
    bootstrap,
    health,
    persistent_auth,
    dashboard,
    login,
    properties,
)

from .monitoring.middleware import PerformanceMonitoringMiddleware

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cache_invalidation_listener():
    """
    Background task to listen for cache invalidation messages from Redis Pub/Sub.
    When a message is received, it invalidates the auth cache for the specified user.
    This ensures cache invalidation works across all worker processes.
    """
    from .core.auth import invalidate_user_cache

    if not redis_client.is_connected:
        logger.info("Redis not connected - cache invalidation listener will not start")
        return

    try:
        # Subscribe to the cache invalidation channel
        pubsub = await redis_client.subscribe("auth_cache_invalidate")
        if not pubsub:
            logger.warning("Failed to subscribe to auth_cache_invalidate channel")
            return

        logger.info("✅ Cache invalidation listener started - listening on auth_cache_invalidate channel")

        # Listen for messages indefinitely
        async for message in pubsub.listen():
            try:
                if message and message.get("type") == "message":
                    user_id = message.get("data")
                    if isinstance(user_id, bytes):
                        user_id = user_id.decode('utf-8')

                    if user_id:
                        # Invalidate cache for this user in the current worker
                        invalidated_count = invalidate_user_cache(user_id)
                        logger.info(f"🔄 Received cache invalidation for user {user_id} - cleared {invalidated_count} entries in this worker")
            except Exception as e:
                logger.error(f"Error processing cache invalidation message: {e}")

    except Exception as e:
        logger.error(f"Cache invalidation listener error: {e}")
    finally:
        try:
            if pubsub:
                await pubsub.unsubscribe("auth_cache_invalidate")
                await pubsub.close()
        except:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up...")

    # Initialize Supabase connection pool
    try:
        from .core.supabase_connection_pool import supabase_pool

        await supabase_pool.initialize()
        logger.info("✅ Supabase connection pool initialized")
    except Exception as e:
        logger.error(f"❌ Supabase connection pool initialization failed: {e}")
        # Continue startup - fallback to direct connections

    # Initialize Redis connection with timeout
    try:
        await redis_client.initialize()
    except Exception as e:
        logger.warning(f"Redis initialization warning: {e}")
        # Continue without Redis - will use fallback

    # Start cache invalidation listener (only if Redis is connected)
    if redis_client.is_connected:
        asyncio.create_task(cache_invalidation_listener())
        logger.info("🔄 Cache invalidation listener task created")
    else:
        logger.info("ℹ️ Redis not connected - cache invalidation will work locally only (single worker mode)")

    # Start async processor background cleanup
    from .core.async_processing import async_processor
    async_processor.start_background_cleanup()
    logger.info("Async processor background cleanup started")

    yield
    # Shutdown
    logger.info("Shutting down...")

    # Shutdown async processor
    await async_processor.shutdown()
    logger.info("Async processor shutdown completed")

    # Close connection pool
    try:
        from .core.supabase_connection_pool import supabase_pool

        await supabase_pool.close()
        logger.info("✅ Supabase connection pool closed")
    except Exception as e:
        logger.warning(f"⚠️ Error closing connection pool: {e}")


app = FastAPI(
    title="Auth Skeleton API",
    description="Authentication and User Management API - Developer Testing Skeleton",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Development
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZIP compression middleware for response optimization
app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
    compresslevel=6
)

# Performance monitoring middleware
app.add_middleware(PerformanceMonitoringMiddleware)

# Include API routers - Auth & User Management Only
# Authentication
app.include_router(login.router, prefix="/api/v1", tags=["auth"])
app.include_router(auth_info.router, prefix="/api/v1", tags=["auth"])
app.include_router(persistent_auth.router, prefix="/api/v1/auth", tags=["persistent-auth"])

# User Management
app.include_router(users_lightning.router, prefix="/api/v1", tags=["users"])
app.include_router(profile.router, prefix="/api/v1", tags=["profile"])

# Dashboard
app.include_router(dashboard.router, prefix="/api/v1", tags=["dashboard"])

# Properties
app.include_router(properties.router, prefix="/api/v1", tags=["properties"])

# Bootstrap & Settings (for AppContext)
app.include_router(company_settings.router, prefix="/api/v1", tags=["company-settings"])
app.include_router(bootstrap.router, prefix="/api/v1", tags=["bootstrap"])

# Departments & Permissions
app.include_router(departments.router, prefix="/api/v1", tags=["departments"])

# Cities (for user access control - used by CityAccessContext)
app.include_router(cities.router, prefix="/api/v1", tags=["cities"])
app.include_router(city_access_fast.router, prefix="/api/v1", tags=["city-access-fast"])
app.include_router(city_access_fixed.router, prefix="/api/v1", tags=["city-access-fixed"])

# Infrastructure
app.include_router(health.router, prefix="/api/v1", tags=["health"])


@app.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    try:
        from .database import supabase

        db_health = await supabase.health_check()
        return {"status": "healthy", "database": db_health}
    except Exception as e:
        return {
            "status": "degraded",
            "database": {"status": "unhealthy", "error": str(e)},
        }


@app.get("/up")
async def up_check():
    return {"status": "up"}


# Database connection pool monitoring endpoints
@app.get("/pool-status")
async def pool_status():
    """Get detailed connection pool status"""
    try:
        from .database import supabase

        pool_status = await supabase.get_pool_status()
        return pool_status
    except Exception as e:
        return {"error": f"Failed to get pool status: {str(e)}"}


@app.get("/database-health")
async def database_health():
    """Detailed database health check"""
    try:
        from .database import supabase

        health_status = await supabase.health_check()
        return health_status
    except Exception as e:
        return {"status": "error", "error": str(e), "timestamp": time.time()}


# Convenience API-prefixed health endpoints for clients that expect them
@app.api_route("/api/v1/health", methods=["GET", "HEAD"])
async def api_health_check():
    try:
        from .database import supabase

        db_health = await supabase.health_check()
        return {"status": "healthy", "database": db_health}
    except Exception as e:
        return {
            "status": "degraded",
            "database": {"status": "unhealthy", "error": str(e)},
        }


@app.get("/api/v1/up")
async def api_up_check():
    return {"status": "up"}


@app.get("/api/v1/pool-status")
async def api_pool_status():
    """Get detailed connection pool status via API"""
    try:
        from .database import supabase

        pool_status = await supabase.get_pool_status()
        return pool_status
    except Exception as e:
        return {"error": f"Failed to get pool status: {str(e)}"}


@app.get("/api/v1/database-health")
async def api_database_health():
    """Detailed database health check via API"""
    try:
        from .database import supabase

        health_status = await supabase.health_check()
        return health_status
    except Exception as e:
        return {"status": "error", "error": str(e), "timestamp": time.time()}


# Circuit breaker management endpoints
@app.post("/api/v1/circuit-breaker/reset")
async def reset_circuit_breaker():
    """Reset circuit breakers to allow operations to resume"""
    try:
        from .core.supabase_connection_pool import supabase_pool
        from .core.async_supabase import connection_tracker

        # Reset connection pool circuit breaker
        if supabase_pool._initialized:
            supabase_pool._circuit_breaker_open = False
            supabase_pool._failed_operations_count = 0
            supabase_pool._circuit_breaker_opened_at = None

        # Reset async supabase connection tracker
        connection_tracker.failed_connections = 0
        connection_tracker.last_failure = None
        connection_tracker.retry_counts.clear()
        connection_tracker.operation_timeouts.clear()

        logger.info("Circuit breakers have been manually reset")

        return {
            "status": "success",
            "message": "Circuit breakers reset successfully",
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Failed to reset circuit breakers: {e}")
        return {"status": "error", "error": str(e), "timestamp": time.time()}


@app.get("/api/v1/circuit-breaker/status")
async def circuit_breaker_status():
    """Get current circuit breaker status"""
    try:
        from .core.supabase_connection_pool import supabase_pool
        from .core.async_supabase import connection_tracker

        status = {
            "connection_pool": {
                "circuit_breaker_open": False,
                "failed_operations_count": 0,
                "circuit_breaker_opened_at": None,
                "threshold": 10,
                "timeout": 60,
            },
            "async_tracker": {
                "failed_connections": connection_tracker.failed_connections,
                "last_failure": connection_tracker.last_failure,
                "should_throttle": connection_tracker.should_throttle(),
                "active_retry_operations": len(connection_tracker.retry_counts),
                "failure_threshold": connection_tracker.failure_threshold,
                "throttle_duration": connection_tracker.throttle_duration,
            },
            "timestamp": time.time(),
        }

        # Get connection pool status if initialized
        if supabase_pool._initialized:
            status["connection_pool"]["circuit_breaker_open"] = (
                supabase_pool._circuit_breaker_open
            )
            status["connection_pool"]["failed_operations_count"] = (
                supabase_pool._failed_operations_count
            )
            status["connection_pool"]["circuit_breaker_opened_at"] = (
                supabase_pool._circuit_breaker_opened_at
            )

        return status
    except Exception as e:
        return {"status": "error", "error": str(e), "timestamp": time.time()}


@app.post("/api/v1/circuit-breaker/configure")
async def configure_circuit_breaker(request: Request):
    """Configure circuit breaker thresholds and timeouts"""
    try:
        body = await request.json()

        from .core.supabase_connection_pool import supabase_pool
        from .core.async_supabase import connection_tracker

        changes_made = []

        # Configure connection pool circuit breaker
        if "pool_threshold" in body:
            supabase_pool._circuit_breaker_threshold = body["pool_threshold"]
            changes_made.append(f"Pool threshold set to {body['pool_threshold']}")

        if "pool_timeout" in body:
            supabase_pool._circuit_breaker_timeout = body["pool_timeout"]
            changes_made.append(f"Pool timeout set to {body['pool_timeout']}s")

        # Configure async tracker thresholds
        if "tracker_threshold" in body:
            connection_tracker.failure_threshold = body["tracker_threshold"]
            changes_made.append(f"Tracker threshold set to {body['tracker_threshold']}")

        if "tracker_timeout" in body:
            connection_tracker.throttle_duration = body["tracker_timeout"]
            changes_made.append(f"Tracker timeout set to {body['tracker_timeout']}s")

        logger.info(f"Circuit breaker configuration updated: {changes_made}")

        return {"status": "success", "changes": changes_made, "timestamp": time.time()}

    except Exception as e:
        logger.error(f"Failed to configure circuit breaker: {e}")
        return {"status": "error", "error": str(e), "timestamp": time.time()}


# Fallback service management endpoints
@app.get("/api/v1/fallback/status")
async def fallback_status():
    """Get fallback service status and cache information"""
    try:
        from .core.circuit_breaker_fallback import fallback_service

        cache_status = fallback_service.get_cache_status()
        return {"status": "active", "cache": cache_status, "timestamp": time.time()}
    except Exception as e:
        return {"status": "error", "error": str(e), "timestamp": time.time()}


@app.post("/api/v1/fallback/clear-cache")
async def clear_fallback_cache():
    """Clear the fallback service cache"""
    try:
        from .core.circuit_breaker_fallback import fallback_service

        fallback_service.clear_cache()
        logger.info("Fallback cache cleared manually")

        return {
            "status": "success",
            "message": "Fallback cache cleared successfully",
            "timestamp": time.time(),
        }
    except Exception as e:
        logger.error(f"Failed to clear fallback cache: {e}")
        return {"status": "error", "error": str(e), "timestamp": time.time()}


# Serve static files (for SPA)
# Check for both static and dist directories (frontend builds to dist)
static_dir = None
if os.path.exists("static"):
    static_dir = "static"
elif os.path.exists("dist"):
    static_dir = "dist"

if static_dir:
    # Mount static files with proper MIME type handling
    if os.path.exists(f"{static_dir}/assets"):
        app.mount(
            "/assets", StaticFiles(directory=f"{static_dir}/assets"), name="assets"
        )
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API routes
        if (
            full_path.startswith("api/")
            or full_path.startswith("health")
            or full_path.startswith("up")
        ):
            raise HTTPException(status_code=404, detail="Not found")

        # Serve static files directly if they exist
        static_file_path = f"{static_dir}/{full_path}"
        if os.path.exists(static_file_path) and os.path.isfile(static_file_path):
            return FileResponse(static_file_path)

        # For all other routes, serve the React app (SPA routing)
        index_path = f"{static_dir}/index.html"
        if os.path.exists(index_path):
            return FileResponse(index_path)

        raise HTTPException(status_code=404, detail="Not found")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
