import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _build_async_database_url() -> str:
    """Translate the configured DATABASE_URL into an asyncpg DSN.

    settings.database_url is the sync/psycopg style URL used everywhere else
    (and the one docker-compose injects), so it has to be re-prefixed before
    SQLAlchemy's async engine will accept it.
    """
    url = settings.database_url
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
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize database connection pool (idempotent)."""
        if self.session_factory:
            return

        async with self._init_lock:
            # Another coroutine may have initialized while we waited.
            if self.session_factory:
                return
            try:
                database_url = _build_async_database_url()

                # Async engines use AsyncAdaptedQueuePool by default; passing the
                # sync QueuePool class here makes create_async_engine raise.
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
                raise

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None

    def get_session(self) -> AsyncSession:
        """Get database session from pool.

        Deliberately synchronous: callers use it as ``async with
        db_pool.get_session() as session``, which needs the session object
        itself rather than a coroutine wrapping it.
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
