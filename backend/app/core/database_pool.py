import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
# from sqlalchemy.pool import QueuePool
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        
    async def initialize(self):
        """Initialize database connection pool"""
        if self.engine and self.session_factory:
            return
        
        try:
            database_url = settings.database_url

            # SQLAlchemy async engine requires the asyncpg driver.
            if database_url.startswith("postgresql://"):
                database_url = database_url.replace(
                    "postgresql://",
                    "postgresql+asyncpg://",
                    1,
                )

            self.engine = create_async_engine(
                database_url,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
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

        except Exception as error:
            logger.exception(
                "Database pool initialization failed: %s",
                error,
            )

            self.engine = None
            self.session_factory = None
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
    
    async def get_session(self) -> AsyncSession:
        """Get database session from pool"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
