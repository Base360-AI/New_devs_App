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
            # The Settings class exposes a single `database_url` (loaded from the
            # DATABASE_URL env var defined in docker-compose). The previous
            # implementation tried to read `supabase_db_user/password/host/port/name`
            # which do not exist on Settings, so the pool initialization silently
            # failed and the revenue service fell back to insecure mock data that
            # ignored the tenant_id. We now use the configured database_url and
            # rewrite the driver scheme to the asyncpg variant required by
            # SQLAlchemy's async engine.
            database_url = settings.database_url
            if database_url.startswith("postgresql://"):
                database_url = "postgresql+asyncpg://" + database_url[len("postgresql://"):]
            elif database_url.startswith("postgres://"):
                database_url = "postgresql+asyncpg://" + database_url[len("postgres://"):]

            self.engine = create_async_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=20,  # Number of connections to maintain
                max_overflow=30,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=3600,  # Recycle connections every hour
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
