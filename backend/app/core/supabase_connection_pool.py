"""
Enhanced Supabase Connection Pool Manager
Fixes connection pool exhaustion and provides comprehensive connection management
"""
import asyncio
import time
import logging
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import threading
from contextlib import asynccontextmanager
from supabase import create_client, Client
from ..config import settings
from .circuit_breaker_fallback import fallback_service

logger = logging.getLogger(__name__)

class GracefulDegradationClient:
    """
    Mock Supabase client that provides fallback responses when circuit breaker is open
    """
    
    def __init__(self, fallback_service):
        self.fallback_service = fallback_service
        
    def table(self, table_name: str):
        """Return a fallback table interface"""
        return GracefulDegradationTable(table_name, self.fallback_service)
    
    def from_(self, table_name: str):
        """Alias for table method"""
        return self.table(table_name)
    
    def rpc(self, function_name: str, params: Dict = None):
        """Return a fallback RPC interface"""
        return GracefulDegradationRPC(function_name, params or {}, self.fallback_service)
    
    @property
    def auth(self):
        """Auth operations not available in fallback mode"""
        return GracefulDegradationAuth(self.fallback_service)
    
    @property
    def storage(self):
        """Storage operations not available in fallback mode"""
        return GracefulDegradationStorage(self.fallback_service)

class GracefulDegradationTable:
    """Mock table interface for graceful degradation"""
    
    def __init__(self, table_name: str, fallback_service):
        self.table_name = table_name
        self.fallback_service = fallback_service
        self.query_params = {}
        
    def select(self, *columns):
        self.query_params['select'] = columns
        return self
    
    def insert(self, data):
        self.query_params['insert'] = data
        return self
    
    def update(self, data):
        self.query_params['update'] = data
        return self
    
    def delete(self):
        self.query_params['delete'] = True
        return self
    
    def eq(self, column, value):
        if 'filters' not in self.query_params:
            self.query_params['filters'] = []
        self.query_params['filters'].append(('eq', column, value))
        return self
    
    def limit(self, count):
        self.query_params['limit'] = count
        return self
    
    def order(self, column, desc=False):
        self.query_params['order'] = (column, desc)
        return self
    
    def execute(self):
        """Return fallback response for the query"""
        # Check if this is a write operation
        if any(key in self.query_params for key in ['insert', 'update', 'delete']):
            return FallbackResponse({
                "error": "Write operations temporarily unavailable",
                "fallback": True,
                "message": "Database is in degraded mode. Write operations are disabled.",
                "retry_after": 60
            })
        
        # Return cached or fallback data for read operations
        return FallbackResponse(
            self.fallback_service.get_fallback_response(self.table_name, self.query_params)
        )

class GracefulDegradationRPC:
    """Mock RPC interface for graceful degradation"""
    
    def __init__(self, function_name: str, params: Dict, fallback_service):
        self.function_name = function_name
        self.params = params
        self.fallback_service = fallback_service
    
    def execute(self):
        """Return fallback response for RPC call"""
        return FallbackResponse(
            self.fallback_service.get_fallback_response(f"rpc_{self.function_name}", self.params)
        )

class GracefulDegradationAuth:
    """Mock auth interface for graceful degradation"""
    
    def __init__(self, fallback_service):
        self.fallback_service = fallback_service
    
    def sign_in_with_password(self, *args, **kwargs):
        return FallbackResponse({
            "error": "Authentication temporarily unavailable",
            "fallback": True,
            "message": "Please try logging in again in a few moments.",
            "retry_after": 30
        })

class GracefulDegradationStorage:
    """Mock storage interface for graceful degradation"""
    
    def __init__(self, fallback_service):
        self.fallback_service = fallback_service
    
    def from_(self, bucket_name):
        return self
    
    def upload(self, *args, **kwargs):
        return FallbackResponse({
            "error": "File upload temporarily unavailable",
            "fallback": True,
            "message": "File operations are disabled while in degraded mode.",
            "retry_after": 60
        })

class FallbackResponse:
    """Mock response object for fallback operations"""
    
    def __init__(self, data):
        self.data = data if isinstance(data, list) else [data] if data else []
        self.count = len(self.data) if isinstance(self.data, list) else 1
        self._fallback = True
    
    def __getattr__(self, name):
        # Return self for method chaining
        return self

class SuccessfulClientWrapper:
    """
    Wrapper for successful Supabase client that caches responses for fallback
    """
    
    def __init__(self, client: Client, fallback_service):
        self._client = client
        self._fallback_service = fallback_service
    
    def table(self, table_name: str):
        """Return a wrapped table that caches responses"""
        return CachingTableWrapper(self._client.table(table_name), table_name, self._fallback_service)
    
    def from_(self, table_name: str):
        """Alias for table method"""
        return self.table(table_name)
    
    def rpc(self, function_name: str, params: Dict = None):
        """Return a wrapped RPC that caches responses"""
        return CachingRPCWrapper(self._client.rpc(function_name, params), function_name, params, self._fallback_service)
    
    @property
    def auth(self):
        """Pass through auth methods unchanged"""
        return self._client.auth
    
    @property
    def storage(self):
        """Pass through storage methods unchanged"""
        return self._client.storage
    
    def __getattr__(self, name):
        """Pass through any other attributes to the real client"""
        return getattr(self._client, name)

class CachingTableWrapper:
    """Wrapper for table operations that caches successful responses"""
    
    def __init__(self, table, table_name: str, fallback_service):
        self._table = table
        self._table_name = table_name
        self._fallback_service = fallback_service
        self._query_params = {}
    
    def select(self, *columns):
        self._query_params['select'] = columns
        return self
    
    def eq(self, column, value):
        if 'filters' not in self._query_params:
            self._query_params['filters'] = []
        self._query_params['filters'].append(('eq', column, value))
        return self
    
    def limit(self, count):
        self._query_params['limit'] = count
        return self
    
    def order(self, column, desc=False):
        self._query_params['order'] = (column, desc)
        return self
    
    def execute(self):
        """Execute the query and cache successful responses"""
        try:
            # Execute the real query
            result = self._table.execute()
            
            # Cache successful read operations for fallback
            if result and hasattr(result, 'data') and 'select' in self._query_params:
                cache_key = self._fallback_service._generate_cache_key(self._table_name, self._query_params)
                self._fallback_service.cache_response(cache_key, {
                    'data': result.data,
                    'count': getattr(result, 'count', len(result.data) if result.data else 0)
                })
            
            return result
        except Exception as e:
            logger.error(f"Table operation failed for {self._table_name}: {e}")
            raise
    
    def __getattr__(self, name):
        """Pass through any other methods to the real table"""
        result = getattr(self._table, name)
        if callable(result):
            def wrapper(*args, **kwargs):
                self._table = result(*args, **kwargs)
                return self
            return wrapper
        return result

class CachingRPCWrapper:
    """Wrapper for RPC operations that caches successful responses"""
    
    def __init__(self, rpc_query, function_name: str, params: Dict, fallback_service):
        self._rpc_query = rpc_query
        self._function_name = function_name
        self._params = params
        self._fallback_service = fallback_service
    
    def execute(self):
        """Execute the RPC and cache successful responses"""
        try:
            result = self._rpc_query.execute()
            
            # Cache successful RPC responses
            if result and hasattr(result, 'data'):
                cache_key = self._fallback_service._generate_cache_key(f"rpc_{self._function_name}", self._params)
                self._fallback_service.cache_response(cache_key, {
                    'data': result.data,
                    'function': self._function_name
                })
            
            return result
        except Exception as e:
            logger.error(f"RPC operation failed for {self._function_name}: {e}")
            raise

@dataclass
class ConnectionMetrics:
    """Track connection pool metrics"""
    total_connections: int = 0
    active_connections: int = 0
    failed_connections: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    average_response_time: float = 0.0
    last_health_check: float = field(default_factory=time.time)
    
class SupabaseConnectionPool:
    """
    Advanced Supabase connection pool with health monitoring, retry logic, and circuit breaker
    """
    
    def __init__(self):
        self.max_connections = settings.supabase_max_concurrent_connections
        self.timeout = settings.supabase_connection_timeout
        self.recycle_interval = settings.supabase_pool_recycle_interval
        
        # Connection management
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=self.max_connections)
        self._clients: List[Client] = []
        self._client_created_times: Dict[Client, float] = {}
        self._active_clients: set = set()
        self._lock = asyncio.Lock()
        
        # Health monitoring
        self.metrics = ConnectionMetrics()
        self._failed_operations_count = 0
        self._circuit_breaker_open = False
        self._circuit_breaker_opened_at = None
        self._circuit_breaker_threshold = 10  # Open after 10 consecutive failures
        self._circuit_breaker_timeout = 60  # Stay open for 60 seconds
        
        # Background tasks
        self._health_monitor_task = None
        self._pool_cleaner_task = None
        self._initialized = False
        
    async def initialize(self):
        """Initialize the connection pool"""
        if self._initialized:
            return

        if not settings.has_supabase_credentials:
            logger.info("Skipping Supabase connection pool initialization in Challenge Mode")
            return
            
        try:
            logger.info(f"Initializing Supabase connection pool with {self.max_connections} connections")
            
            # Create initial pool of connections
            for i in range(min(10, self.max_connections)):  # Start with 10 connections
                client = self._create_client()
                self._clients.append(client)
                self._client_created_times[client] = time.time()
                await self._pool.put(client)
            
            self.metrics.total_connections = len(self._clients)
            
            # Start background tasks
            self._health_monitor_task = asyncio.create_task(self._health_monitor())
            self._pool_cleaner_task = asyncio.create_task(self._pool_cleaner())
            
            self._initialized = True
            logger.info(f"✅ Supabase connection pool initialized with {len(self._clients)} connections")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase connection pool: {e}")
            raise
    
    def _create_client(self) -> Client:
        """Create a new Supabase client"""
        return create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
    
    @asynccontextmanager
    async def get_client(self):
        """Get a client from the pool with automatic return and graceful degradation"""
        if self._circuit_breaker_open:
            if time.time() - self._circuit_breaker_opened_at < self._circuit_breaker_timeout:
                # Circuit breaker is open - provide graceful degradation
                logger.warning("Circuit breaker is open - providing fallback responses")
                yield GracefulDegradationClient(fallback_service)
                return
            else:
                # Try to close circuit breaker
                self._circuit_breaker_open = False
                self._failed_operations_count = 0
                logger.info("Circuit breaker closed - attempting to resume operations")
        
        client = None
        start_time = time.time()
        
        try:
            # Try to get a client from pool
            try:
                client = await asyncio.wait_for(self._pool.get(), timeout=self.timeout)
            except asyncio.TimeoutError:
                # Pool is empty, try to create a new client if we haven't hit the limit
                async with self._lock:
                    if len(self._clients) < self.max_connections:
                        client = self._create_client()
                        self._clients.append(client)
                        self._client_created_times[client] = time.time()
                        self.metrics.total_connections += 1
                        logger.info(f"Created new client, pool size now: {len(self._clients)}")
                    else:
                        raise Exception(f"Connection pool exhausted ({self.max_connections} connections)")
            
            if client:
                self._active_clients.add(client)
                self.metrics.active_connections += 1
                
                yield SuccessfulClientWrapper(client, fallback_service)
                
                # Operation successful
                self._failed_operations_count = 0
                self.metrics.successful_operations += 1
                
        except Exception as e:
            # Operation failed
            self._failed_operations_count += 1
            self.metrics.failed_operations += 1
            
            # Check if we should open circuit breaker
            if self._failed_operations_count >= self._circuit_breaker_threshold:
                self._circuit_breaker_open = True
                self._circuit_breaker_opened_at = time.time()
                logger.error(f"Circuit breaker opened after {self._failed_operations_count} consecutive failures")
            
            logger.error(f"Supabase operation failed: {e}")
            raise
            
        finally:
            if client:
                # Update metrics
                duration = time.time() - start_time
                total_ops = self.metrics.successful_operations + self.metrics.failed_operations
                if total_ops > 0:
                    self.metrics.average_response_time = (
                        (self.metrics.average_response_time * (total_ops - 1) + duration) / total_ops
                    )
                
                # Return client to pool
                if client in self._active_clients:
                    self._active_clients.remove(client)
                    self.metrics.active_connections -= 1
                
                # Check if client should be recycled
                if self._should_recycle_client(client):
                    await self._recycle_client(client)
                else:
                    await self._pool.put(client)
    
    def _should_recycle_client(self, client: Client) -> bool:
        """Check if client should be recycled"""
        if client not in self._client_created_times:
            return True
        
        client_age = time.time() - self._client_created_times[client]
        return client_age > self.recycle_interval
    
    async def _recycle_client(self, client: Client):
        """Recycle an old client"""
        try:
            # Remove from tracking
            if client in self._clients:
                self._clients.remove(client)
            if client in self._client_created_times:
                del self._client_created_times[client]
            
            # Create new client
            new_client = self._create_client()
            self._clients.append(new_client)
            self._client_created_times[new_client] = time.time()
            
            # Add new client to pool
            await self._pool.put(new_client)
            
            logger.debug("Recycled old Supabase client")
            
        except Exception as e:
            logger.error(f"Failed to recycle client: {e}")
            # Put the old client back if recycling failed
            await self._pool.put(client)
    
    async def _health_monitor(self):
        """Background task to monitor connection health"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self._check_pool_health()
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
    
    async def _pool_cleaner(self):
        """Background task to clean up stale connections"""
        while True:
            try:
                await asyncio.sleep(300)  # Clean every 5 minutes
                await self._cleanup_stale_connections()
            except Exception as e:
                logger.error(f"Pool cleaner error: {e}")
    
    async def _check_pool_health(self):
        """Check the health of the connection pool"""
        try:
            self.metrics.last_health_check = time.time()
            
            # Log pool status
            available_connections = self._pool.qsize()
            logger.info(
                f"Pool Health: {available_connections}/{self.metrics.total_connections} available, "
                f"{self.metrics.active_connections} active, "
                f"Success rate: {self._get_success_rate():.1f}%"
            )
            
            # Ensure minimum number of connections
            min_connections = max(5, self.max_connections // 4)
            if available_connections < min_connections:
                async with self._lock:
                    connections_to_create = min_connections - available_connections
                    connections_to_create = min(connections_to_create, self.max_connections - len(self._clients))
                    
                    for _ in range(connections_to_create):
                        client = self._create_client()
                        self._clients.append(client)
                        self._client_created_times[client] = time.time()
                        await self._pool.put(client)
                        self.metrics.total_connections += 1
                    
                    if connections_to_create > 0:
                        logger.info(f"Added {connections_to_create} connections to maintain minimum pool size")
            
        except Exception as e:
            logger.error(f"Pool health check failed: {e}")
    
    async def _cleanup_stale_connections(self):
        """Remove stale connections from the pool"""
        try:
            stale_clients = []
            current_time = time.time()
            
            # Find stale clients
            for client, created_time in self._client_created_times.items():
                if current_time - created_time > self.recycle_interval and client not in self._active_clients:
                    stale_clients.append(client)
            
            # Remove stale clients
            for client in stale_clients:
                if client in self._clients:
                    self._clients.remove(client)
                if client in self._client_created_times:
                    del self._client_created_times[client]
                self.metrics.total_connections -= 1
            
            if stale_clients:
                logger.info(f"Cleaned up {len(stale_clients)} stale connections")
                
        except Exception as e:
            logger.error(f"Connection cleanup failed: {e}")
    
    def _get_success_rate(self) -> float:
        """Calculate success rate percentage"""
        total = self.metrics.successful_operations + self.metrics.failed_operations
        if total == 0:
            return 100.0
        return (self.metrics.successful_operations / total) * 100
    
    def get_pool_status(self) -> Dict[str, Any]:
        """Get detailed pool status"""
        return {
            "total_connections": self.metrics.total_connections,
            "available_connections": self._pool.qsize(),
            "active_connections": self.metrics.active_connections,
            "successful_operations": self.metrics.successful_operations,
            "failed_operations": self.metrics.failed_operations,
            "success_rate": self._get_success_rate(),
            "average_response_time": self.metrics.average_response_time,
            "circuit_breaker_open": self._circuit_breaker_open,
            "last_health_check": self.metrics.last_health_check,
            "max_connections": self.max_connections
        }
    
    async def close(self):
        """Close the connection pool"""
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
        if self._pool_cleaner_task:
            self._pool_cleaner_task.cancel()
        
        logger.info("Supabase connection pool closed")

# Global connection pool instance
supabase_pool = SupabaseConnectionPool()

async def get_supabase_client():
    """Dependency to get a managed Supabase client"""
    if not settings.has_supabase_credentials:
        raise RuntimeError("Supabase client requested while running in Challenge Mode")
    if not supabase_pool._initialized:
        await supabase_pool.initialize()
    
    async with supabase_pool.get_client() as client:
        yield client
