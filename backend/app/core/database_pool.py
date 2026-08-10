import asyncio
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _async_dsn(url: str) -> str:
    """
    Normalises a libpq-style URL into an asyncpg one.

    docker-compose supplies DATABASE_URL=postgresql://... , which SQLAlchemy would
    hand to psycopg2 (a sync driver) and refuse to use behind create_async_engine.
    """
    for prefix in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if url.startswith(prefix):
            return url
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool"""
        try:
            database_url = _async_dsn(settings.database_url)

            # NOTE: no explicit poolclass here. An asyncio engine needs an
            # async-aware pool; SQLAlchemy picks AsyncAdaptedQueuePool by default.
            # Forcing the sync QueuePool raises at engine creation time.
            self.engine = create_async_engine(
                database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout,
                pool_pre_ping=True,  # Validate connections
                pool_recycle=settings.database_pool_recycle,
                echo=False,  # Set to True for SQL debugging
            )

            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            logger.info("✅ Database connection pool initialized")

        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None
            raise

    async def ensure_initialized(self):
        """Initialize once, on first use. Safe to await from concurrent requests."""
        if self.session_factory:
            return
        async with self._lock:
            if not self.session_factory:
                await self.initialize()

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    def get_session(self) -> AsyncSession:
        """Get a database session from the pool.

        Deliberately NOT async: the caller uses it as `async with pool.get_session()`,
        and `async with` on a coroutine object fails with AttributeError __aenter__.
        """
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        return self.session_factory()

    @asynccontextmanager
    async def session(self):
        """Context manager that opens a session and always closes it."""
        await self.ensure_initialized()
        session = self.get_session()
        try:
            yield session
        finally:
            await session.close()


# Global database pool instance
db_pool = DatabasePool()


async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.session() as session:
        yield session
