import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.database_pool import DatabasePool


class DatabasePoolTests(unittest.IsolatedAsyncioTestCase):
    def test_normalizes_postgresql_urls_for_asyncpg(self):
        self.assertEqual(
            DatabasePool._async_database_url(
                "postgresql://user:password@database:5432/propertyflow"
            ),
            "postgresql+asyncpg://user:password@database:5432/propertyflow",
        )
        self.assertEqual(
            DatabasePool._async_database_url(
                "postgresql+asyncpg://user:password@database/propertyflow"
            ),
            "postgresql+asyncpg://user:password@database/propertyflow",
        )

    @patch("app.core.database_pool.async_sessionmaker")
    @patch("app.core.database_pool.create_async_engine")
    async def test_pool_can_close_and_reinitialize(
        self,
        create_engine: MagicMock,
        create_session_factory: MagicMock,
    ):
        first_engine = MagicMock()
        first_engine.dispose = AsyncMock()
        second_engine = MagicMock()
        second_engine.dispose = AsyncMock()
        create_engine.side_effect = [first_engine, second_engine]
        create_session_factory.side_effect = [MagicMock(), MagicMock()]
        pool = DatabasePool()

        await pool.initialize()
        await pool.initialize()

        create_engine.assert_called_once()
        self.assertIs(pool.engine, first_engine)

        await pool.close()

        first_engine.dispose.assert_awaited_once()
        self.assertIsNone(pool.engine)
        self.assertIsNone(pool.session_factory)

        await pool.initialize()

        self.assertEqual(create_engine.call_count, 2)
        self.assertIs(pool.engine, second_engine)


if __name__ == "__main__":
    unittest.main()
