import asyncio

from app.core import database_pool


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


class FakeConnectionContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeEngine:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.disposed = False

    def connect(self) -> FakeConnectionContext:
        return FakeConnectionContext(self.connection)

    async def dispose(self) -> None:
        self.disposed = True


def test_database_pool_uses_configured_database_url(monkeypatch) -> None:
    captured: dict = {}
    fake_engine = FakeEngine()

    def fake_create_async_engine(url: str, **kwargs) -> FakeEngine:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return fake_engine

    monkeypatch.setattr(
        database_pool.settings,
        "database_url",
        "postgresql://app_user:secret@db:5432/propertyflow",
    )
    monkeypatch.setattr(
        database_pool,
        "create_async_engine",
        fake_create_async_engine,
    )

    pool = database_pool.DatabasePool()
    asyncio.run(pool.initialize())

    assert captured["url"] == (
        "postgresql+asyncpg://app_user:secret@db:5432/propertyflow"
    )
    assert fake_engine.connection.statements == ["SELECT 1"]
    assert pool.session_factory is not None

    asyncio.run(pool.close())
    assert fake_engine.disposed is True

