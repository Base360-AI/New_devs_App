import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from ..config import settings

logger = logging.getLogger(__name__)


def _async_database_url() -> str:
    """Build the asyncpg URL from the configured database_url."""
    url = settings.database_url
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize the database connection pool.

        Safe to call more than once: only the first call builds the engine.
        Raises if the database cannot actually be reached, so a broken pool can
        never be mistaken for a working one.
        """
        if self.session_factory is not None:
            return

        async with self._lock:
            if self.session_factory is not None:
                return

            database_url = _async_database_url()

            # No poolclass here: an asyncio engine requires AsyncAdaptedQueuePool,
            # which create_async_engine selects by default. Passing the sync
            # QueuePool raises ArgumentError.
            engine = create_async_engine(
                database_url,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections on checkout
                pool_recycle=3600,  # Recycle connections every hour
                echo=False,  # Set to True for SQL debugging
            )

            try:
                # create_async_engine is lazy, so connect once here. Without this
                # the success log below would say nothing about reachability.
                async with engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
            except Exception:
                await engine.dispose()
                logger.exception("❌ Database pool initialization failed")
                raise

            self.engine = engine
            self.session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.info("✅ Database connection pool initialized and verified")

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        """Get a database session from the pool, closing it on exit."""
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        async with self.session_factory() as session:
            yield session


# Global database pool instance
db_pool = DatabasePool()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Dependency to get database session"""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
