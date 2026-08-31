import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._initialize_lock = asyncio.Lock()
        
    async def initialize(self) -> bool:
        """Initialize and verify the shared database connection pool once."""
        if self.session_factory:
            return True

        candidate_engine = None
        try:
            async with self._initialize_lock:
                if self.session_factory:
                    return True

                database_url = settings.database_url.replace(
                    "postgresql://",
                    "postgresql+asyncpg://",
                    1,
                )

                candidate_engine = create_async_engine(
                    database_url,
                    pool_size=20,
                    max_overflow=30,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                    echo=False,
                )

                async with candidate_engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))

                self.engine = candidate_engine
                self.session_factory = async_sessionmaker(
                    bind=self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                )

                logger.info("✅ Database connection pool initialized")
                return True
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            if candidate_engine:
                await candidate_engine.dispose()
            self.engine = None
            self.session_factory = None
            return False
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
        self.engine = None
        self.session_factory = None
    
    def get_session(self) -> AsyncSession:
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
