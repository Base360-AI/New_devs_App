import asyncio
import logging
from typing import AsyncIterator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

logger = logging.getLogger(__name__)


class DatabasePoolError(RuntimeError):
    """Raised when the application database pool is unavailable."""


class DatabasePool:
    def __init__(self) -> None:
        self.engine = None
        self.session_factory = None
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the shared SQLAlchemy async engine once."""
        if self.session_factory is not None:
            return

        async with self._initialize_lock:
            if self.session_factory is not None:
                return

            try:
                database_url = make_url(settings.database_url).set(
                    drivername="postgresql+asyncpg"
                )
                engine = create_async_engine(
                    database_url,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_timeout=settings.database_pool_timeout,
                    pool_pre_ping=True,
                    pool_recycle=settings.database_pool_recycle,
                    echo=False,
                )
                self.engine = engine
                self.session_factory = async_sessionmaker(
                    bind=engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
                logger.info("Database connection pool initialized")
            except Exception as exc:
                self.engine = None
                self.session_factory = None
                logger.exception("Database pool initialization failed")
                raise DatabasePoolError("Database pool initialization failed") from exc

    async def close(self) -> None:
        """Close all shared database connections."""
        engine = self.engine
        self.engine = None
        self.session_factory = None
        if engine is not None:
            await engine.dispose()

    def get_session(self) -> AsyncSession:
        """Create a session backed by the shared async engine."""
        if self.session_factory is None:
            raise DatabasePoolError("Database pool is not initialized")
        return self.session_factory()


db_pool = DatabasePool()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for a shared-pool database session."""
    async with db_pool.get_session() as session:
        yield session
