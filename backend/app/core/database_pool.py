import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    """Use the asyncpg driver for a plain postgresql:// URL."""
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool (once per process)"""
        if self.session_factory:
            return
        async with self._init_lock:
            if self.session_factory:
                return
            await self._create_engine()

    async def _create_engine(self):
        try:
            # The async engine uses AsyncAdaptedQueuePool by default.
            # QueuePool is not valid for asyncio engines.
            self.engine = create_async_engine(
                _async_database_url(settings.database_url),
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,  # Validate connections
                pool_recycle=settings.database_pool_recycle,
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
        """Get database session from pool"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
