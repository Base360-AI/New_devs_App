import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._initialization_lock = asyncio.Lock()

    @staticmethod
    def _async_database_url(database_url: str) -> str:
        """Normalize common PostgreSQL URLs for SQLAlchemy's async driver."""
        if database_url.startswith("postgresql://"):
            return database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        if database_url.startswith("postgres://"):
            return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return database_url
        
    async def initialize(self):
        """Initialize the shared async database connection pool once."""
        if self.session_factory:
            return

        async with self._initialization_lock:
            if self.session_factory:
                return

            try:
                self.engine = create_async_engine(
                    self._async_database_url(settings.database_url),
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                    pool_timeout=settings.database_pool_timeout,
                    pool_recycle=settings.database_pool_recycle,
                    pool_pre_ping=True,
                    echo=False,
                )

                self.session_factory = async_sessionmaker(
                    bind=self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )
                logger.info("PostgreSQL connection pool initialized")
            except Exception:
                logger.exception("Database pool initialization failed")
                if self.engine:
                    await self.engine.dispose()
                self.engine = None
                self.session_factory = None
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None
    
    def get_session(self) -> AsyncSession:
        """Get database session from pool"""
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
