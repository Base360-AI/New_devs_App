from typing import Any, Optional
from supabase import create_client, Client
from .config import settings
from .core.tenant_context import get_user_token
from .core.supabase_connection_pool import supabase_pool
import logging
import time
import asyncio
import hashlib
import jwt

logger = logging.getLogger(__name__)


class TenantAwareSupabase:
    """Lightweight wrapper that applies the current request's bearer token
    to PostgREST calls (table/from/rpc), so RLS + current_tenant_id() work
    without modifying individual queries.

    It preserves access to admin endpoints like auth.admin via the underlying
    service role client.
    """

    def __init__(self, base: Client) -> None:
        self._base = base
        self._active_connections = 0
        self._max_concurrent = settings.supabase_max_concurrent_connections
        self._connection_semaphore = asyncio.Semaphore(self._max_concurrent)
        self._failure_count = 0
        self._last_failure = None
        self._connection_timeout = getattr(settings, 'supabase_connection_timeout', 30.0)
        self._connection_start_times = {}
        self._cleanup_threshold = 60.0  # Force cleanup connections older than 60 seconds
        
        # CIRCUIT BREAKER: Prevent cascading failures
        self._circuit_breaker_threshold = 10  # Open circuit after 10 failures
        self._circuit_breaker_timeout = 60  # Keep circuit open for 60 seconds
        self._circuit_open = False
        self._circuit_opened_at = None

    def _apply_auth(self) -> None:
        # Apply the per-request bearer token for PostgREST calls if present
        token = get_user_token()
        try:
            # Get the postgrest client
            postgrest = getattr(self._base, "postgrest", None) or getattr(self._base, "_postgrest", None)
            if postgrest and token:
                # Set the Authorization header directly on the postgrest client
                if hasattr(postgrest, 'headers'):
                    postgrest.headers['Authorization'] = f'Bearer {token}'
                elif hasattr(postgrest, 'session') and hasattr(postgrest.session, 'headers'):
                    postgrest.session.headers['Authorization'] = f'Bearer {token}'
                elif hasattr(postgrest, 'auth'):
                    # Try the auth method as fallback
                    postgrest.auth(token)
            elif postgrest and not token:
                # Reset to service role key when no user token
                from .config import settings
                service_key = settings.supabase_service_role_key
                if hasattr(postgrest, 'headers'):
                    postgrest.headers['Authorization'] = f'Bearer {service_key}'
                elif hasattr(postgrest, 'session') and hasattr(postgrest.session, 'headers'):
                    postgrest.session.headers['Authorization'] = f'Bearer {service_key}'
        except Exception as e:
            # Log the error but continue with service role
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to apply user token to PostgREST client: {str(e)}")
            pass

    def _cleanup_stale_connections(self):
        """Clean up connections that have been active for too long"""
        current_time = time.time()
        stale_connections = [
            conn_id for conn_id, start_time in self._connection_start_times.items()
            if current_time - start_time > self._cleanup_threshold
        ]
        
        if stale_connections:
            logger.warning(f"Cleaning up {len(stale_connections)} stale connections")
            for conn_id in stale_connections:
                self._connection_start_times.pop(conn_id, None)
            # Reset connection count if we have stale tracking
            if len(stale_connections) > 0:
                self._active_connections = max(0, self._active_connections - len(stale_connections))

    def _check_circuit_breaker(self):
        """Check circuit breaker state and manage failures"""
        current_time = time.time()
        
        # Check if circuit should be closed (reset after timeout)
        if self._circuit_open and self._circuit_opened_at:
            if current_time - self._circuit_opened_at > self._circuit_breaker_timeout:
                logger.info("Circuit breaker timeout expired, closing circuit")
                self._circuit_open = False
                self._circuit_opened_at = None
                self._failure_count = 0  # Reset failure count
        
        # Open circuit if failure threshold exceeded
        if not self._circuit_open and self._failure_count >= self._circuit_breaker_threshold:
            logger.error(f"Circuit breaker OPENED after {self._failure_count} failures")
            self._circuit_open = True
            self._circuit_opened_at = current_time
        
        return self._circuit_open

    # PostgREST entry points with connection limiting and timeout handling
    def table(self, name: str):
        connection_id = id(self)
        start_time = time.time()
        
        # CIRCUIT BREAKER: Fail fast if circuit is open
        if self._check_circuit_breaker():
            raise HTTPException(
                status_code=503,
                detail="Database circuit breaker is OPEN due to recent failures. Please try again in a moment."
            )
        
        self._cleanup_stale_connections()
        
        # Quick connection limiting with timeout
        if self._active_connections >= self._max_concurrent:
            logger.warning(f"Connection limit reached ({self._active_connections}/{self._max_concurrent})")
            # Use shorter delay to prevent request pileup
            time.sleep(0.05)
            
            # If still at limit after delay, raise exception instead of blocking
            if self._active_connections >= self._max_concurrent:
                raise HTTPException(
                    status_code=503, 
                    detail="Database connection pool exhausted. Please try again in a moment."
                )
        
        self._active_connections += 1
        self._connection_start_times[connection_id] = start_time
        
        try:
            self._apply_auth()
            
            # Apply connection timeout
            result = self._base.table(name)
            self._failure_count = 0  # Reset on success
            return result
            
        except Exception as e:
            self._failure_count += 1
            self._last_failure = time.time()
            logger.error(f"Table operation failed after {time.time() - start_time:.2f}s: {e}")
            raise
        finally:
            self._active_connections = max(0, self._active_connections - 1)
            self._connection_start_times.pop(connection_id, None)

    # Some code may call .from("table") style; provide alias
    def from_(self, name: str):
        return self.table(name)

    def rpc(self, fn: str, params: Optional[dict] = None):
        # Quick connection limiting
        if self._active_connections >= self._max_concurrent:
            logger.warning(f"Connection limit reached ({self._active_connections}/{self._max_concurrent})")
            time.sleep(0.1)  # Brief delay
            
        self._active_connections += 1
        try:
            self._apply_auth()
            result = self._base.rpc(fn, params or {})
            self._failure_count = 0  # Reset on success
            return result
        except Exception as e:
            self._failure_count += 1
            self._last_failure = time.time()
            logger.error(f"RPC operation failed: {e}")
            raise
        finally:
            self._active_connections = max(0, self._active_connections - 1)

    # Expose underlying clients unchanged
    @property
    def auth(self):
        return self._base.auth

    @property
    def storage(self):
        return self._base.storage

    @property
    def service(self) -> Client:
        """Access the underlying service-role client for trusted server-side queries.
        Use sparingly and always scope by tenant_id derived from the user's token/claims.
        """
        return self._base

    def __getattr__(self, item: str) -> Any:
        # Fallback passthrough for any other attributes
        return getattr(self._base, item)
    
    async def get_pool_status(self) -> dict:
        """Get connection pool status for monitoring"""
        try:
            if not settings.has_supabase_credentials:
                return {
                    "status": "challenge_mode",
                    "message": "Supabase connection pool is disabled; using mock Supabase client and local Postgres challenge data.",
                    "timestamp": time.time(),
                }
            if not supabase_pool._initialized:
                await supabase_pool.initialize()
            return supabase_pool.get_pool_status()
        except Exception as e:
            logger.error(f"Failed to get pool status: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> dict:
        """Perform a health check on the database connection"""
        try:
            if not settings.has_supabase_credentials:
                return {
                    "status": "challenge_mode",
                    "database": "local_postgres",
                    "supabase_pool": "disabled",
                    "timestamp": time.time(),
                }
            if not supabase_pool._initialized:
                await supabase_pool.initialize()
            
            # Test a simple query
            async with supabase_pool.get_client() as client:
                # Simple health check query
                result = client.table('users').select('id').limit(1)
                
            pool_status = supabase_pool.get_pool_status()
            
            return {
                "status": "healthy",
                "connection_pool": pool_status,
                "timestamp": time.time()
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def execute_with_pool(self, operation_func, *args, **kwargs):
        """Execute an operation using the connection pool"""
        try:
            if not settings.has_supabase_credentials:
                raise RuntimeError("Supabase pooled operations are unavailable in Challenge Mode")
            if not supabase_pool._initialized:
                await supabase_pool.initialize()
            
            async with supabase_pool.get_client() as client:
                # Apply tenant context to the pooled client
                self._apply_auth_to_client(client)
                return await operation_func(client, *args, **kwargs)
                
        except Exception as e:
            logger.error(f"Pooled operation failed: {e}")
            raise
    
    def _apply_auth_to_client(self, client: Client):
        """Apply the current request's bearer token to a specific client"""
        token = get_user_token()
        try:
            # Get the postgrest client
            postgrest = getattr(client, "postgrest", None) or getattr(client, "_postgrest", None)
            if postgrest and token:
                # Set the Authorization header directly on the postgrest client
                if hasattr(postgrest, 'headers'):
                    postgrest.headers['Authorization'] = f'Bearer {token}'
                elif hasattr(postgrest, 'session') and hasattr(postgrest.session, 'headers'):
                    postgrest.session.headers['Authorization'] = f'Bearer {token}'
                elif hasattr(postgrest, 'auth'):
                    # Try the auth method as fallback
                    postgrest.auth(token)
            elif postgrest and not token:
                # Reset to service role key when no user token
                service_key = settings.supabase_service_role_key
                if hasattr(postgrest, 'headers'):
                    postgrest.headers['Authorization'] = f'Bearer {service_key}'
                elif hasattr(postgrest, 'session') and hasattr(postgrest.session, 'headers'):
                    postgrest.session.headers['Authorization'] = f'Bearer {service_key}'
        except Exception as e:
            # Log the error but continue with service role
            logger.warning(f"Failed to apply user token to PostgREST client: {str(e)}")


# Base Supabase client with enhanced configuration
try:
    if settings.supabase_url and settings.supabase_service_role_key:
        _base_client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key
        )
        supabase: TenantAwareSupabase = TenantAwareSupabase(_base_client)
    else:
        # Fallback mode: Supabase client is not available.
        logger.warning("Supabase URL/Key not set. Running in Challenge Mode (Mock Client).")
        
        class MockUser:
            def __init__(self, email="candidate@propertyflow.com", role="admin", name="Candidate User"):
                self.id = hashlib.md5(email.encode()).hexdigest()
                self.email = email
                self.app_metadata = {"role": role, "tenant_id": "tenant-a"}
                self.user_metadata = {"name": name}
                self.created_at = "2024-01-01T00:00:00Z"
                self.last_sign_in_at = "2024-01-01T00:00:00Z"

        class MockResponse:
            def __init__(self, user=None, data=None):
                self.user = user
                self.data = data if data is not None else []

        class ChallengeAuth:
            def get_user(self, token):
                # Validate the mock token used by frontend
                if token == "mock-token-123":
                    return MockResponse(user=MockUser())
                
                # Try to decode the JWT token generated by our login endpoint
                try:
                    # Parse payload in fallback mode.
                    import jwt
                    payload = jwt.decode(token, options={"verify_signature": False})
                    email = payload.get("email")
                    if email:
                        users = self.list_users()
                        for u in users:
                            if u.email == email:
                                return MockResponse(user=u)
                except Exception:
                    pass
                    
                # Return empty response (sets user=None) which simulates invalid token
                return MockResponse(user=None)
            
            @property
            def admin(self):
                return self
                
            def list_users(self):
                # Return a list of mock users to support login testing
                return [
                    MockUser("candidate@propertyflow.com", "admin", "Candidate User"),
                    MockUser("manager@sunset.com", "user", "Manager User"),
                    MockUser("sid@theflexliving.com", "admin", "Sid"),
                    MockUser("raouf@theflexliving.com", "admin", "Raouf"),
                    MockUser("michael@theflexliving.com", "admin", "Michael")
                ]

            def get_user_by_id(self, user_id):
                users = self.list_users()
                for u in users:
                    if u.id == user_id:
                        return MockResponse(user=u)
                return MockResponse(user=None)

        class ChallengeClient:
            def __init__(self):
                self.auth = ChallengeAuth()
                self.service = self

            def __getattr__(self, name):
                # Return self for chaining (e.g. table().select())
                return lambda *args, **kwargs: self
            
            def table(self, *args):
                 return self
            
            def select(self, *args):
                return self
            
            def eq(self, *args):
                return self
                
            def in_(self, *args):
                return self

            def execute(self):
                # Return empty data for DB queries
                return MockResponse()

        _base_client = ChallengeClient()
        supabase = ChallengeClient() # Type: ignore

except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    # Fallback
    class DummyClient:
        def __getattr__(self, name):
            return lambda *args, **kwargs: None
    supabase = DummyClient()
