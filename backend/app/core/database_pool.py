import asyncio
from contextlib import asynccontextmanager
import logging

import asyncpg

from ..config import settings

logger = logging.getLogger(__name__)


def _asyncpg_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + url[len("postgresql+asyncpg://"):]
    if url.startswith("postgres+asyncpg://"):
        return "postgresql://" + url[len("postgres+asyncpg://"):]
    return url


class DatabasePool:
    def __init__(self):
        self.pool = None
        self._init_lock = asyncio.Lock()

    async def initialize(self):
        if self.pool:
            return

        async with self._init_lock:
            if self.pool:
                return

            try:
                self.pool = await asyncpg.create_pool(
                    _asyncpg_database_url(settings.database_url),
                    min_size=1,
                    max_size=20,
                )
                logger.info("Database connection pool initialized")
            except Exception as e:
                logger.error(f"Database pool initialization failed: {e}")
                self.pool = None

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def get_connection(self):
        if not self.pool:
            await self.initialize()
        if not self.pool:
            raise Exception("Database pool not initialized")
        async with self.pool.acquire() as connection:
            yield connection

# Global database pool instance
db_pool = DatabasePool()

async def get_db_session():
    async with db_pool.get_connection() as connection:
        yield connection
