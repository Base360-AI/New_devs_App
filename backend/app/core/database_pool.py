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
        try:
            # Create async engine with connection pooling
            # Prefer a single DATABASE_URL if provided (convert to asyncpg driver),
            # otherwise fall back to legacy separate supabase_db_* settings.
            database_url = None
            try:
                database_url = getattr(settings, 'database_url', None)
            except Exception:
                database_url = None

            if database_url:
                # Convert sync driver to asyncpg driver
                if database_url.startswith('postgresql://'):
                    database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
            else:
                database_url = f"postgresql+asyncpg://{settings.supabase_db_user}:{settings.supabase_db_password}@{settings.supabase_db_host}:{settings.supabase_db_port}/{settings.supabase_db_name}"
            
            self.engine = create_async_engine(
                database_url,
                echo=False  # Set to True for SQL debugging
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
            raise Exception("Database pool not initialized")
        return self.session_factory()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
