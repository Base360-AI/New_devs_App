import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool
from ..config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._loop = None
        self._lock = None
        
    def _get_database_url(self) -> str:
        url = settings.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    def _get_lock(self):
        current_loop = asyncio.get_running_loop()
        if self._lock is None or self._loop != current_loop:
            self._lock = asyncio.Lock()
        return self._lock

    async def initialize(self):
        """Initialize database connection pool"""
        current_loop = asyncio.get_running_loop()
        if self.engine is not None and self.session_factory is not None and self._loop == current_loop:
            return

        lock = self._get_lock()
        async with lock:
            if self.engine is not None and self.session_factory is not None and self._loop == current_loop:
                return

            if self.engine is not None and self._loop != current_loop:
                try:
                    await self.engine.dispose()
                except Exception:
                    pass
                self.engine = None
                self.session_factory = None

            try:
                database_url = self._get_database_url()

                self.engine = create_async_engine(
                    database_url,
                    poolclass=AsyncAdaptedQueuePool,
                    pool_size=getattr(settings, "database_pool_size", 20),
                    max_overflow=getattr(settings, "database_max_overflow", 30),
                    pool_timeout=getattr(settings, "database_pool_timeout", 30),
                    pool_pre_ping=True,
                    pool_recycle=getattr(settings, "database_pool_recycle", 3600),
                    echo=False
                )

                self.session_factory = async_sessionmaker(
                    bind=self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False
                )
                self._loop = current_loop

                logger.info("✅ Database connection pool initialized")

            except Exception as e:
                logger.error(f"❌ Database pool initialization failed: {e}")
                self.engine = None
                self.session_factory = None
                self._loop = None
                raise
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None
            self._loop = None
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session from pool supporting 'async with' context manager"""
        current_loop = asyncio.get_running_loop()
        if not self.session_factory or self._loop != current_loop:
            await self.initialize()
        if not self.session_factory:
            raise RuntimeError("Database pool not initialized")
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session"""
    async with db_pool.get_session() as session:
        yield session
