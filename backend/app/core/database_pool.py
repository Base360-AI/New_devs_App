from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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
            database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

            self.engine = create_async_engine(
                database_url,
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

    @asynccontextmanager
    async def tenant_session(self, tenant_id: str):
        """Session bound to one tenant. Postgres RLS reads app.tenant_id.

        set_config(..., true) is transaction-local, so a pooled connection
        never carries a previous tenant into the next request.
        """
        if not tenant_id:
            raise PermissionError("tenant_id required")
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        async with self.session_factory() as session, session.begin():
            await session.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
            yield session

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
