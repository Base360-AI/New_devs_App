import unittest
from unittest.mock import patch

from app.core.database_pool import DatabasePool


class RevenueDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_pool_uses_configured_database_url(self):
        pool = DatabasePool()

        with patch(
            "app.core.database_pool.create_async_engine"
        ) as create_engine:
            await pool.initialize()

        database_url = str(create_engine.call_args.args[0])
        self.assertEqual(
            database_url,
            "postgresql+asyncpg://postgres:postgres@db:5432/propertyflow",
        )


if __name__ == "__main__":
    unittest.main()
