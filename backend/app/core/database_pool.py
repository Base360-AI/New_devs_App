from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..config import settings


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self) -> None:
        """Initialize the asynchronous database connection pool."""
        if self.session_factory is not None:
            return

        database_url = settings.database_url
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://",
                "postgresql+asyncpg://",
                1,
            )

        self.engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False,
        )

        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    def get_session(self) -> AsyncSession:
        """Create a database session."""
        if self.session_factory is None:
            raise RuntimeError("Database pool is not initialized")

        return self.session_factory()

    async def close(self) -> None:
        """Close the database connection pool."""
        if self.engine is not None:
            await self.engine.dispose()

        self.engine = None
        self.session_factory = None


db_pool = DatabasePool()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that provides a database session."""
    if db_pool.session_factory is None:
        await db_pool.initialize()

    async with db_pool.get_session() as session:
        yield session