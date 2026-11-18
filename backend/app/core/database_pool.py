import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url

from ..config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Initialize the async pool from the configured DATABASE_URL."""
        if self.session_factory:
            return
        try:
            database_url = make_url(settings.database_url)
            if database_url.drivername in {"postgres", "postgresql"}:
                database_url = database_url.set(drivername="postgresql+asyncpg")
            self.engine = create_async_engine(
                database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_pre_ping=True,
                pool_recycle=settings.database_pool_recycle,
                echo=False,
            )
            self.session_factory = async_sessionmaker(
                bind=self.engine, class_=AsyncSession, expire_on_commit=False
            )
            logger.info("Database connection pool initialized")
        except Exception:
            logger.exception("Database pool initialization failed")
            self.engine = None
            self.session_factory = None
            raise

    async def close(self):
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    def get_session(self) -> AsyncSession:
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        return self.session_factory()


db_pool = DatabasePool()


async def get_db_session():
    if not db_pool.session_factory:
        await db_pool.initialize()
    async with db_pool.get_session() as session:
        yield session
