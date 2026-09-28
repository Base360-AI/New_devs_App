import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

logger = logging.getLogger(__name__)

def _async_database_url(database_url: str) -> str:
    """Return a SQLAlchemy URL that uses the asyncpg driver."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


class DatabasePool:
    """Lazily initialized async SQLAlchemy session factory."""

    def __init__(self) -> None:
        self.engine = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None
        self._initialization_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the shared pool once using the configured DATABASE_URL."""
        if self.session_factory is not None:
            return

        async with self._initialization_lock:
            if self.session_factory is not None:
                return

            database_url = _async_database_url(settings.database_url)
            self.engine = create_async_engine(
                database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout,
                pool_pre_ping=True,
                pool_recycle=settings.database_pool_recycle,
                echo=False,
            )
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.info("Database connection pool initialized")

    async def close(self) -> None:
        """Dispose of the database engine during application shutdown."""
        engine = self.engine
        self.engine = None
        self.session_factory = None
        if engine is not None:
            await engine.dispose()

    def get_session(self) -> AsyncSession:
        """Create a session from the initialized factory."""
        if self.session_factory is None:
            raise RuntimeError("Database pool has not been initialized")
        return self.session_factory()


# One shared pool prevents a new engine from being created for every request.
db_pool = DatabasePool()


async def get_db_session():
    """FastAPI dependency that yields an initialized database session."""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
