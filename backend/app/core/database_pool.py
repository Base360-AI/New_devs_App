import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _to_asyncpg_url(url: str) -> str:
    """Normalise a Postgres URL onto the asyncpg driver expected by the async engine."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool"""
        if self.session_factory:
            return

        async with self._lock:
            # Another coroutine may have initialized while we waited for the lock.
            if self.session_factory:
                return
            try:
                # Built from DATABASE_URL, which docker-compose points at the app database.
                database_url = _to_asyncpg_url(settings.database_url)

                # No explicit poolclass: the async engine supplies AsyncAdaptedQueuePool,
                # and passing the sync QueuePool here is rejected.
                self.engine = create_async_engine(
                    database_url,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_pre_ping=True,  # Validate connections
                    pool_recycle=settings.database_pool_recycle,
                    echo=False,  # Set to True for SQL debugging
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
        """Get database session from pool.

        Returns the session itself (not a coroutine) so callers can use
        `async with db_pool.get_session() as session:`.
        """
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
