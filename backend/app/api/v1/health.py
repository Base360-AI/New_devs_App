"""
Health Check API for monitoring backend performance and reliability
Provides detailed status information for diagnosing 504 timeout issues
Enhanced with cache management capabilities
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional
from ...database import supabase
from ...core.redis_client import redis_client
from ...core.tenant_cache import tenant_cache
from ...core.async_processing import async_processor
from ...core.auth import authenticate_request, require_admin
from ...models.auth import AuthenticatedUser
import time
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])

@router.get("/status")
async def get_health_status(
    _user: AuthenticatedUser = Depends(require_admin),
) -> Dict[str, Any]:
    """
    Comprehensive health check for backend components
    Used to diagnose 504 timeout issues and system performance
    """
    start_time = time.time()
    status = {
        "timestamp": datetime.now().isoformat(),
        "status": "healthy",
        "checks": {},
        "performance": {}
    }
    
    # Database health check
    try:
        db_start = time.time()
        # Simple query to test database connectivity
        result = supabase.service.table('tenants').select('id').limit(1).execute()
        db_duration = time.time() - db_start
        
        status["checks"]["database"] = {
            "status": "healthy",
            "response_time_ms": round(db_duration * 1000, 2),
            "details": "Connection successful"
        }
        
        # Get connection pool status
        pool_status = await supabase.get_pool_status()
        status["checks"]["database"]["pool"] = pool_status
        
    except Exception as e:
        status["checks"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "Database connection failed"
        }
        status["status"] = "degraded"
    
    # Redis health check
    try:
        redis_start = time.time()
        if redis_client:
            await redis_client.ping()
            redis_duration = time.time() - redis_start
            
            status["checks"]["redis"] = {
                "status": "healthy",
                "response_time_ms": round(redis_duration * 1000, 2),
                "details": "Connection successful"
            }
        else:
            status["checks"]["redis"] = {
                "status": "unavailable",
                "details": "Redis client not initialized"
            }
    except Exception as e:
        status["checks"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
            "details": "Redis connection failed"
        }
    
    # Circuit breaker status
    try:
        circuit_status = {
            "open": supabase._circuit_open,
            "failure_count": supabase._failure_count,
            "last_failure": supabase._last_failure,
            "active_connections": supabase._active_connections,
            "max_connections": supabase._max_concurrent
        }
        status["checks"]["circuit_breaker"] = circuit_status
        
        if supabase._circuit_open:
            status["status"] = "degraded"
            
    except Exception as e:
        status["checks"]["circuit_breaker"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Overall performance metrics
    total_duration = time.time() - start_time
    status["performance"] = {
        "total_response_time_ms": round(total_duration * 1000, 2),
        "healthy_components": len([c for c in status["checks"].values() if c.get("status") == "healthy"]),
        "total_components": len(status["checks"])
    }
    
    db_healthy = status["checks"].get("database", {}).get("status") == "healthy"
    if not db_healthy:
        status["status"] = "unhealthy"
    
    logger.info(f"Health check completed in {total_duration:.3f}s - Status: {status['status']}")
    return status

@router.get("/db")
async def get_database_health(
    _user: AuthenticatedUser = Depends(require_admin),
) -> Dict[str, Any]:
    """Detailed database health check for performance monitoring"""
    start_time = time.time()
    
    try:
        # Test multiple database operations
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "tests": {}
        }
        
        # Test 1: Simple connection
        test_start = time.time()
        result = supabase.service.table('tenants').select('id').limit(1).execute()
        health_data["tests"]["connection"] = {
            "duration_ms": round((time.time() - test_start) * 1000, 2),
            "status": "success" if result.data else "no_data"
        }
        
        # Test 2: Properties query (common in city access)
        test_start = time.time()
        props = supabase.service.table('all_properties').select('id, city').limit(10).execute()
        health_data["tests"]["properties_query"] = {
            "duration_ms": round((time.time() - test_start) * 1000, 2),
            "records_returned": len(props.data) if props.data else 0
        }
        
        # Test 3: User tenants lookup (common in auth)
        test_start = time.time()
        users = supabase.service.table('user_tenants').select('user_id').limit(5).execute()
        health_data["tests"]["user_tenants_query"] = {
            "duration_ms": round((time.time() - test_start) * 1000, 2),
            "records_returned": len(users.data) if users.data else 0
        }
        
        # Connection pool status
        health_data["connection_pool"] = await supabase.get_pool_status()
        
        # Circuit breaker status
        health_data["circuit_breaker"] = {
            "open": supabase._circuit_open,
            "failure_count": supabase._failure_count,
            "active_connections": supabase._active_connections,
            "max_connections": supabase._max_concurrent
        }
        
        total_duration = time.time() - start_time
        health_data["total_duration_ms"] = round(total_duration * 1000, 2)
        health_data["status"] = "healthy"
        
        return health_data
        
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "unhealthy",
            "error": str(e),
            "duration_ms": round((time.time() - start_time) * 1000, 2)
        }

@router.get("/performance")
async def get_performance_metrics(
    _user: AuthenticatedUser = Depends(require_admin),
) -> Dict[str, Any]:
    """Get performance metrics for identifying bottlenecks"""
    try:
        # Measure key operation response times
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "database": {},
            "cache": {},
            "connection_pool": {}
        }
        
        # Database response time
        db_start = time.time()
        test_query = supabase.service.table('cleaning_reports').select('id').limit(1).execute()
        metrics["database"]["query_response_ms"] = round((time.time() - db_start) * 1000, 2)
        
        # Redis response time (if available)
        if redis_client:
            try:
                redis_start = time.time()
                await redis_client.ping()
                metrics["cache"]["ping_response_ms"] = round((time.time() - redis_start) * 1000, 2)
            except Exception as e:
                metrics["cache"]["error"] = str(e)
        
        # Connection pool metrics
        metrics["connection_pool"] = {
            "active": supabase._active_connections,
            "max": supabase._max_concurrent,
            "utilization_pct": round((supabase._active_connections / supabase._max_concurrent) * 100, 2),
            "failure_count": supabase._failure_count,
            "circuit_open": supabase._circuit_open
        }
        
        return metrics
        
    except Exception as e:
        logger.error(f"Performance metrics failed: {e}")
        raise HTTPException(status_code=500, detail="Performance metrics are temporarily unavailable")

@router.post("/warm-cache")
async def warm_cache_for_user(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(authenticate_request)
) -> Dict[str, Any]:
    """
    Warm cache for a specific user to improve performance
    Admin endpoint for proactive cache management
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    if not user_id:
        user_id = user.id  # Warm cache for requesting user if not specified
    
    try:
        start_time = time.time()
        
        # Warm cache for the specified user
        warming_results = await tenant_cache.warm_cache_for_user(user_id, tenant_id)
        
        duration_ms = round((time.time() - start_time) * 1000, 2)
        
        return {
            "status": "success",
            "user_id": user_id,
            "tenant_id": tenant_id,
            "warming_results": warming_results,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache warming failed: {e}")
        raise HTTPException(status_code=500, detail="Cache warming failed")

@router.post("/invalidate-cache")
async def invalidate_cache_endpoint(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    city: Optional[str] = None,
    cache_type: Optional[str] = None,  # user, tenant, city, or all
    user: AuthenticatedUser = Depends(authenticate_request)
) -> Dict[str, Any]:
    """
    Invalidate specific cache entries for troubleshooting
    Admin endpoint for cache management
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        keys_cleared = 0
        
        if cache_type == "all" or not any([user_id, tenant_id, city]):
            # Clear all tenant-related caches (use with caution)
            if tenant_id:
                keys_cleared = await tenant_cache.invalidate_tenant_cache(tenant_id)
            else:
                return {"status": "error", "message": "tenant_id required for 'all' cache clear"}
        
        elif cache_type == "user" or user_id:
            # Clear user-specific caches
            if user_id:
                keys_cleared = await tenant_cache.invalidate_user_cache(user_id)
            else:
                return {"status": "error", "message": "user_id required for user cache clear"}
        
        elif cache_type == "tenant" or tenant_id:
            # Clear tenant-specific caches
            if tenant_id:
                keys_cleared = await tenant_cache.invalidate_tenant_cache(tenant_id)
            else:
                return {"status": "error", "message": "tenant_id required for tenant cache clear"}
        
        elif cache_type == "city" or city:
            # Clear city-specific caches
            if city:
                keys_cleared = await tenant_cache.invalidate_city_cache(city)
            else:
                return {"status": "error", "message": "city required for city cache clear"}
        
        return {
            "status": "success",
            "keys_cleared": keys_cleared,
            "cache_type": cache_type,
            "parameters": {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "city": city
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        raise HTTPException(status_code=500, detail="Cache invalidation failed")

@router.get("/cache-stats")
async def get_cache_statistics(
    user: AuthenticatedUser = Depends(authenticate_request)
) -> Dict[str, Any]:
    """
    Get cache statistics and health information
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # Get Redis connection info
        redis_stats = {
            "connected": redis_client.is_connected,
            "client_available": redis_client.redis_client is not None
        }
        
        if redis_client.is_connected:
            try:
                # Get basic Redis info
                info = await redis_client.redis_client.info()
                redis_stats.update({
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0)
                })
                
                # Calculate hit rate
                hits = info.get("keyspace_hits", 0)
                misses = info.get("keyspace_misses", 0)
                total_requests = hits + misses
                hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0
                redis_stats["hit_rate_percentage"] = round(hit_rate, 2)
                
            except Exception as e:
                redis_stats["error"] = str(e)
        
        return {
            "status": "success",
            "redis": redis_stats,
            "tenant_cache": {
                "service_available": True,
                "ttl_settings": {
                    "user_tenants_ttl": tenant_cache.user_tenants_ttl,
                    "city_access_ttl": tenant_cache.city_access_ttl,
                    "property_access_ttl": tenant_cache.property_access_ttl,
                    "tenant_config_ttl": tenant_cache.tenant_config_ttl
                }
            },
            "async_processor": async_processor.get_stats(),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail="Cache statistics are temporarily unavailable")

@router.get("/task-status/{task_id}")
async def get_task_status(
    task_id: str,
    user: AuthenticatedUser = Depends(authenticate_request)
) -> Dict[str, Any]:
    """
    Get status of a specific async task
    """
    try:
        task = await async_processor.get_task_status(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Verify user can access this task
        if task.user_id != user.id and not user.is_admin:
            raise HTTPException(status_code=403, detail="Access denied to this task")
        
        response = {
            "task_id": task.id,
            "name": task.name,
            "status": task.status.value,
            "progress": task.progress,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error": task.error
        }
        
        # Include result if completed
        if task.status.value == "completed" and task.result:
            response["result"] = task.result
            
        # Include result size info if available
        if task.result and isinstance(task.result, dict):
            if 'items' in task.result:
                response["result_size"] = len(task.result['items'])
            if 'processing_time_ms' in task.result:
                response["processing_time_ms"] = task.result['processing_time_ms']
        
        # Calculate processing time if available
        if task.started_at and task.completed_at:
            processing_time = (task.completed_at - task.started_at).total_seconds()
            response["processing_time_seconds"] = round(processing_time, 2)
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail="Task status is temporarily unavailable")

@router.post("/cancel-task/{task_id}")
async def cancel_task(
    task_id: str,
    user: AuthenticatedUser = Depends(authenticate_request)
) -> Dict[str, Any]:
    """
    Cancel a running async task
    """
    try:
        task = await async_processor.get_task_status(task_id)
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Verify user can cancel this task
        if task.user_id != user.id and not user.is_admin:
            raise HTTPException(status_code=403, detail="Access denied to this task")
        
        success = await async_processor.cancel_task(task_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Task {task_id} has been cancelled",
                "task_id": task_id
            }
        else:
            return {
                "status": "failed",
                "message": f"Task {task_id} could not be cancelled (may already be completed)",
                "task_id": task_id
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task: {e}")
        raise HTTPException(status_code=500, detail="Task cancellation failed")

@router.get("/user-tasks")
async def get_user_tasks(
    user: AuthenticatedUser = Depends(authenticate_request)
) -> Dict[str, Any]:
    """
    Get all async tasks for the current user
    """
    try:
        user_tasks = await async_processor.get_user_tasks(user.id)
        
        tasks_data = []
        for task in user_tasks:
            task_data = {
                "task_id": task.id,
                "name": task.name,
                "status": task.status.value,
                "progress": task.progress,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "error": task.error
            }
            
            # Add result size info if completed
            if task.status.value == "completed" and task.result:
                if isinstance(task.result, dict) and 'items' in task.result:
                    task_data["result_count"] = len(task.result['items'])
                if isinstance(task.result, dict) and 'processing_time_ms' in task.result:
                    task_data["processing_time_ms"] = task.result['processing_time_ms']
            
            tasks_data.append(task_data)
        
        # Sort by creation time, newest first
        tasks_data.sort(key=lambda x: x['created_at'], reverse=True)
        
        return {
            "tasks": tasks_data,
            "total": len(tasks_data),
            "active_count": len([t for t in tasks_data if t['status'] in ['pending', 'in_progress']]),
            "completed_count": len([t for t in tasks_data if t['status'] == 'completed']),
            "failed_count": len([t for t in tasks_data if t['status'] == 'failed'])
        }
        
    except Exception as e:
        logger.error(f"Failed to get user tasks: {e}")
        raise HTTPException(status_code=500, detail="Task lookup is temporarily unavailable")

@router.get("/async-stats")
async def get_async_processor_stats(
    user: AuthenticatedUser = Depends(authenticate_request)
) -> Dict[str, Any]:
    """
    Get async processor statistics and performance metrics
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        stats = async_processor.get_stats()
        
        return {
            "status": "success",
            "async_processor": stats,
            "background_cleanup_running": async_processor._cleanup_task is not None and not async_processor._cleanup_task.done(),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get async stats: {e}")
        raise HTTPException(status_code=500, detail="Async statistics are temporarily unavailable")
