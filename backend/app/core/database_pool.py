import asyncio
import asyncpg
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.pool = None
        
    async def initialize(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=1,
                max_size=20  # Number of connections to maintain
            )
            
            logger.info("✅ Database connection pool initialized")
            
        except Exception as e:
            logger.error(f"❌ Database pool initialization failed: {e}")
            self.pool = None
            raise
    
    async def close(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()
            self.pool = None
    
    def get_session(self):
        """Get database connection from pool (use with `async with`)"""
        if not self.pool:
            raise Exception("Database pool not initialized")
        return self.pool.acquire()

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session():
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
