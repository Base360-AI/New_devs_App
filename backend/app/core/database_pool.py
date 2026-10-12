import asyncio
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def build_async_database_url(database_url: str) -> str:
    """
    Normalises a libpq-style URL to the asyncpg driver SQLAlchemy needs.

    docker-compose supplies DATABASE_URL as postgresql://..., which
    create_async_engine rejects because it resolves to the sync psycopg2
    driver.
    """
    if database_url.startswith("postgresql+"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool"""
        # Idempotent: callers initialize per request, and building a new engine
        # each time would leak connection pools.
        if self.session_factory:
            return

        async with self._init_lock:
            if self.session_factory:
                return

            try:
                database_url = build_async_database_url(settings.database_url)

                # No poolclass: create_async_engine selects AsyncAdaptedQueuePool.
                # Passing the sync QueuePool here raises at engine creation.
                self.engine = create_async_engine(
                    database_url,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_timeout=settings.database_pool_timeout,
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
                # Do not leave the pool silently unusable: callers that treat a
                # missing session_factory as "no data" would report wrong
                # figures rather than an outage.
                logger.error(f"❌ Database pool initialization failed: {e}")
                self.engine = None
                self.session_factory = None
                raise

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    @asynccontextmanager
    async def get_session(self):
        """Get database session from pool"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        async with self.session_factory() as session:
            yield session

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
