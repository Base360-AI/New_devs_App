import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Initialize the shared asynchronous database connection pool."""
        if self.engine is not None:
            return

        database_url = settings.database_url
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

        try:
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

            async with self.engine.connect() as connection:
                await connection.exec_driver_sql("SELECT 1")

            logger.info("Database connection pool initialized")
        except Exception:
            if self.engine is not None:
                await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            logger.exception("Database connection pool initialization failed")
            raise

    async def close(self):
        """Close database connections."""
        if self.engine is not None:
            await self.engine.dispose()

        self.engine = None
        self.session_factory = None

    def get_session(self) -> AsyncSession:
        """Create a session from the initialized pool."""
        if self.session_factory is None:
            raise RuntimeError("Database pool is not initialized")

        return self.session_factory()


db_pool = DatabasePool()


async def get_db_session() -> AsyncSession:
    """FastAPI dependency that provides a database session."""
    async with db_pool.get_session() as session:
        yield session
