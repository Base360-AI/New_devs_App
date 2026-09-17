from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import logging
from ..config import settings

logger = logging.getLogger(__name__)


def _to_asyncpg_url(url: str) -> str:
    """Normalize sync Postgres URLs to the asyncpg SQLAlchemy dialect."""
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None

    async def initialize(self):
        """Initialize database connection pool"""
        if self.session_factory is not None:
            return

        try:
            # Use the compose/local DATABASE_URL, not legacy Supabase host fields.
            database_url = _to_asyncpg_url(settings.database_url)

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

            logger.info("✅ Database connection pool initialized")

        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.engine = None
            self.session_factory = None

    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    async def get_session(self) -> AsyncSession:
        """Get database session from pool"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()


# Global database pool instance
db_pool = DatabasePool()


async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.session_factory() as session:
        yield session
