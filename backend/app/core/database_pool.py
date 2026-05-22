import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Initialize database connection pool"""
        try:
            # Build the async engine URL from the configured database_url. The
            # previous code referenced settings.supabase_db_* fields that don't
            # exist on Settings, so this raised AttributeError on every request,
            # silently disabling the pool and forcing the mock-data fallback in
            # calculate_total_revenue (which leaked prop-001 across tenants).
            # Use the real DATABASE_URL and the asyncpg driver.
            database_url = settings.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

            # Note: don't pass poolclass=QueuePool here -- create_async_engine
            # rejects the sync QueuePool and uses an async-compatible pool by
            # default. pool_size/max_overflow still apply.
            self.engine = create_async_engine(
                database_url,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=3600,  # Recycle connections every hour
                echo=False  # Set to True for SQL debugging
            )
            
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("✅ Database connection pool initialized")
            
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
    
    def get_session(self) -> AsyncSession:
        """Get a database session from the pool.

        This is intentionally a plain (non-async) method: callers use it as
        ``async with db_pool.get_session() as session``. session_factory()
        returns an AsyncSession, which IS the async context manager. When this
        was ``async def`` it returned a coroutine, so ``async with`` failed with
        "'coroutine' object does not support the asynchronous context manager
        protocol".
        """
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
