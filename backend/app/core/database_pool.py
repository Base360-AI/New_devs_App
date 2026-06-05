import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from ..config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    @staticmethod
    def _build_async_url() -> str:
        """Normalise the configured DB URL to use the asyncpg driver."""
        url = settings.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return url.replace(prefix, "postgresql+asyncpg://", 1)
        return url

    async def initialize(self):
        """Build the connection pool once; safe to call repeatedly."""
        if self.session_factory is not None:
            return

        try:
            self.engine = create_async_engine(
                self._build_async_url(),
                pool_size=20,
                max_overflow=30,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error("Database pool initialization failed: %s", e)
            self.engine = None
            self.session_factory = None

    async def close(self):
        if self.engine:
            await self.engine.dispose()

    def get_session(self) -> AsyncSession:
        """Return a session; use as ``async with db_pool.get_session() as session:``."""
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        return self.session_factory()


db_pool = DatabasePool()


async def get_db_session() -> AsyncSession:
    async with db_pool.get_session() as session:
        yield session
