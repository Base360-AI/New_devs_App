import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    """Convert a plain postgresql:// URL into the asyncpg driver form."""
    for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool (idempotent)"""
        if self.session_factory:
            return
        async with self._lock:
            if self.session_factory:
                return
            try:
                # Async engines use AsyncAdaptedQueuePool by default
                self.engine = create_async_engine(
                    _async_database_url(settings.database_url),
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
            self.engine = None
            self.session_factory = None

    def get_session(self) -> AsyncSession:
        """Get database session from pool (use with `async with`)"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
