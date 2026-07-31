from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import AsyncAdaptedQueuePool
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _async_database_url(url: str) -> str:
    """Convert a sync Postgres URL to an asyncpg SQLAlchemy URL."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Initialize database connection pool (idempotent)."""
        if self.session_factory is not None:
            return

        try:
            database_url = _async_database_url(settings.database_url)

            self.engine = create_async_engine(
                database_url,
                poolclass=AsyncAdaptedQueuePool,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=3600,  # Recycle connections every hour
                echo=False  # Set to True for SQL debugging
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

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    def get_session(self) -> AsyncSession:
        """Return a new AsyncSession from the shared pool (sync — not a coroutine)."""
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        return self.session_factory()


# Global database pool instance — reuse this; do not construct a new engine per request.
db_pool = DatabasePool()


async def get_db_session() -> AsyncSession:
    """FastAPI dependency that yields a database session."""
    await db_pool.initialize()
    session = db_pool.get_session()
    try:
        yield session
    finally:
        await session.close()
