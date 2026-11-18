import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
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
                pool_size=settings.database_pool_size,  # Number of connections to maintain
                max_overflow=settings.database_max_overflow,  # Additional connections when needed
                pool_pre_ping=True,  # Validate connections
                pool_recycle=settings.database_pool_recycle,  # Recycle connections every hour
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
    
    def get_session(self) -> AsyncSession:
        """Get database session from pool"""
        if not self.session_factory:
            raise Exception("Database pool not initialized")
        return self.session_factory()

    @asynccontextmanager
    async def tenant_session(self, tenant_id: str) -> AsyncIterator[AsyncSession]:
        """Get a session whose queries are limited to one tenant by row level security"""
        if not tenant_id:
            raise ValueError("tenant_id is required for a tenant session")
        if not self.session_factory:
            await self.initialize()
        if not self.session_factory:
            raise Exception("Database pool not available")

        async with self.session_factory() as session:
            async with session.begin():
                # is_local=true scopes the setting to this transaction only
                await session.execute(
                    text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
                    {"tenant_id": tenant_id}
                )
                yield session

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncSession:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
