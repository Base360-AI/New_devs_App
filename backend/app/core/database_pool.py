import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        
    async def initialize(self):
        """Initialize database connection pool"""
        if self.session_factory:
            return

        try:
            # Create async engine with connection pooling from settings.database_url
            db_url = settings.database_url
            if db_url.startswith("postgresql://"):
                database_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif db_url.startswith("postgres://"):
                database_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            else:
                database_url = db_url
            
            self.engine = create_async_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=getattr(settings, 'database_pool_size', 20),
                max_overflow=getattr(settings, 'database_max_overflow', 30),
                pool_pre_ping=True,
                pool_recycle=getattr(settings, 'database_pool_recycle', 3600),
                echo=False
            )
            
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
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
    
    async def get_session(self) -> AsyncSession:
        """Get database session from pool"""
        if not self.session_factory:
            await self.initialize()
        if not self.session_factory:
            raise Exception("Database pool not available")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
