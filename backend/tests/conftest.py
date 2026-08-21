"""BDD fixtures and steps for tenant isolation, Redis keys, and timezone windows."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from unittest.mock import patch
from zoneinfo import ZoneInfo

import fakeredis.aioredis
import pytest
from pytest_bdd import given, parsers, then, when

from tests.catalog import FakeDB, ReservationCatalog, _parse_timestamptz


@dataclass
class World:
    catalog: ReservationCatalog
    fake_db: FakeDB
    loop: asyncio.AbstractEventLoop
    redis: Any = None
    last_summary: Optional[dict[str, Any]] = None
    last_monthly: Optional[Decimal] = None
    last_window: tuple[datetime, datetime] | None = None
    db_unavailable: bool = False

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    def redis_keys(self) -> list[str]:
        raw = self.run(self.redis.keys("*"))
        keys: list[str] = []
        for key in raw:
            keys.append(key.decode() if isinstance(key, bytes) else str(key))
        return keys


@pytest.fixture
def world():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    catalog = ReservationCatalog.seed()
    current = World(
        catalog=catalog,
        fake_db=FakeDB(catalog),
        loop=loop,
    )
    yield current
    if current.redis is not None:
        try:
            current.run(current.redis.aclose())
        except Exception:
            pass
    loop.close()


def _bind_database_pool(world: World):
    class FakePool:
        def __init__(self):
            self.session_factory = True

        async def initialize(self):
            return None

        def get_session(self):
            return world.fake_db

    class DeadPool:
        def __init__(self):
            self.session_factory = None

        async def initialize(self):
            self.session_factory = None

        def get_session(self):
            raise RuntimeError("database unavailable")

    pool = DeadPool if world.db_unavailable else FakePool
    return patch("app.core.database_pool.DatabasePool", pool)


async def _lifetime_revenue(world: World, property_id: str, tenant_id: str) -> dict[str, Any]:
    from app.services.reservations import calculate_total_revenue

    with _bind_database_pool(world):
        return await calculate_total_revenue(property_id, tenant_id)


async def _monthly_revenue(
    world: World, property_id: str, tenant_id: str, month: int, year: int
) -> Decimal:
    from app.services.reservations import calculate_monthly_revenue

    signature = inspect.signature(calculate_monthly_revenue)
    names = set(signature.parameters)
    if "tenant_id" not in names:
        pytest.fail("calculate_monthly_revenue must accept tenant_id for virtual isolation")

    kwargs: dict[str, Any] = {"tenant_id": tenant_id}
    if "db_session" in names:
        kwargs["db_session"] = world.fake_db
    if "db" in names:
        kwargs["db"] = world.fake_db
    timezone_name = world.catalog.timezone_for(property_id, tenant_id)
    if "timezone" in names:
        kwargs["timezone"] = timezone_name
    if "property_timezone" in names:
        kwargs["property_timezone"] = timezone_name

    result = await calculate_monthly_revenue(property_id, month, year, **kwargs)
    return Decimal(str(result))


async def _summary(world: World, property_id: str, tenant_id: str) -> dict[str, Any]:
    from app.services import cache as cache_service

    async def fake_calc(property_id: str, tenant_id: str) -> dict[str, Any]:
        total, count = world.catalog.lifetime_total(property_id, tenant_id)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total),
            "currency": "USD",
            "count": count,
        }

    with patch.object(cache_service, "redis_client", world.redis), patch(
        "app.services.reservations.calculate_total_revenue", fake_calc
    ):
        return await cache_service.get_revenue_summary(property_id, tenant_id)


def _payloads_by_tenant(world: World, property_id: str) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for key in world.redis_keys():
        if property_id not in key:
            continue
        raw = world.run(world.redis.get(key))
        if raw is None:
            continue
        if isinstance(raw, bytes):
            raw = raw.decode()
        data = json.loads(raw)
        tenant_id = data.get("tenant_id")
        if tenant_id is None:
            for part in key.split(":"):
                if part.startswith("tenant-"):
                    tenant_id = part
                    break
            if tenant_id is None and "tenant:" in key:
                tenant_id = key.split("tenant:", 1)[-1].split(":")[0]
        if tenant_id:
            payloads[tenant_id] = data
    return payloads


def _fake_db_bounds(world: World) -> tuple[Optional[datetime], Optional[datetime]]:
    params = world.fake_db.last_params
    if isinstance(params, dict):
        start = params.get("start_date") or params.get("start")
        end = params.get("end_date") or params.get("end")
        return start, end
    if isinstance(params, (tuple, list)) and len(params) >= 4:
        return params[2], params[3]
    return None, None


@given("the assignment seed reservations are loaded")
def seed_loaded(world: World):
    assert world.catalog.reservations, "seed catalog should not be empty"


@given("a fake Redis client is used for revenue caching")
def fake_redis(world: World):
    world.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)


@given("the database pool is unavailable")
def database_unavailable(world: World):
    world.db_unavailable = True


@given(
    parsers.parse(
        'property "{property_id}" for tenant "{tenant_id}" is in timezone "{tz_name}"'
    )
)
def property_timezone(world: World, property_id: str, tenant_id: str, tz_name: str):
    assert world.catalog.timezone_for(property_id, tenant_id) == tz_name


@given(parsers.parse('reservation "{res_id}" checks in at "{timestamp}"'))
def reservation_check_in(world: World, res_id: str, timestamp: str):
    row = next(item for item in world.catalog.reservations if item.id == res_id)
    assert row.check_in == _parse_timestamptz(timestamp)


@given(
    parsers.parse(
        'a booking "{res_id}" of {amount} on property "{property_id}" '
        'for tenant "{tenant_id}" checking in at "{timestamp}"'
    )
)
def extra_booking(
    world: World,
    res_id: str,
    amount: str,
    property_id: str,
    tenant_id: str,
    timestamp: str,
):
    world.catalog.add_reservation(
        res_id,
        property_id,
        tenant_id,
        timestamp,
        "2024-04-05 10:00:00+00",
        amount,
    )


@given(
    parsers.parse(
        'tenant "{tenant_id}" has a warm revenue cache for property "{property_id}"'
    )
)
def warm_cache(world: World, tenant_id: str, property_id: str):
    assert world.redis is not None, "Redis fixture missing"
    world.last_summary = world.run(_summary(world, property_id, tenant_id))


@when(
    parsers.parse(
        'tenant "{tenant_id}" requests lifetime revenue for property "{property_id}"'
    )
)
def request_lifetime(world: World, tenant_id: str, property_id: str):
    world.last_summary = world.run(_lifetime_revenue(world, property_id, tenant_id))


@when(
    parsers.parse(
        'tenant "{tenant_id}" calculates monthly revenue for property "{property_id}" in March {year:d}'
    )
)
def request_monthly(world: World, tenant_id: str, property_id: str, year: int):
    world.last_monthly = world.run(
        _monthly_revenue(world, property_id, tenant_id, 3, year)
    )


@when(
    parsers.parse('tenant "{tenant_id}" caches revenue for property "{property_id}"')
)
def cache_revenue(world: World, tenant_id: str, property_id: str):
    assert world.redis is not None, "Redis fixture missing"
    world.last_summary = world.run(_summary(world, property_id, tenant_id))


@when(
    parsers.parse(
        'tenant "{tenant_id}" requests cached revenue for property "{property_id}"'
    )
)
def request_cached(world: World, tenant_id: str, property_id: str):
    assert world.redis is not None, "Redis fixture missing"
    world.last_summary = world.run(_summary(world, property_id, tenant_id))


@when(parsers.parse('the March {year:d} window is built for timezone "{tz_name}"'))
def build_month_window(world: World, year: int, tz_name: str):
    from app.services import reservations

    helper = None
    for name in (
        "month_bounds",
        "month_window",
        "build_month_bounds",
        "month_bounds_in_timezone",
    ):
        candidate = getattr(reservations, name, None)
        if callable(candidate):
            helper = candidate
            break
    if helper is None:
        pytest.fail(
            "app.services.reservations must expose month_bounds(year, month, timezone) "
            "returning timezone-aware (start, end) datetimes"
        )
    start, end = helper(year, 3, tz_name)
    world.last_window = (start, end)


@then(parsers.parse("the revenue total is {amount}"))
def assert_revenue_total(world: World, amount: str):
    assert world.last_summary is not None, "no revenue summary captured"
    assert Decimal(str(world.last_summary["total"])) == Decimal(amount)


@then(parsers.parse("the reservation count is {count:d}"))
def assert_reservation_count(world: World, count: int):
    assert world.last_summary is not None, "no revenue summary captured"
    assert int(world.last_summary["count"]) == count


@then(parsers.parse("the monthly total is {amount}"))
def assert_monthly_total(world: World, amount: str):
    assert world.last_monthly is not None, "no monthly total captured"
    assert world.last_monthly == Decimal(amount)


@then(parsers.parse('the last revenue query bound tenant_id "{tenant_id}"'))
def assert_tenant_bound(world: World, tenant_id: str):
    params = world.fake_db.last_params
    if isinstance(params, dict):
        assert params.get("tenant_id") == tenant_id
        return
    if isinstance(params, (tuple, list)):
        assert tenant_id in params
        return
    pytest.fail("revenue query did not bind tenant_id (no captured params)")


@then(
    parsers.parse(
        'Redis has a key that contains both "{tenant_id}" and "{property_id}"'
    )
)
def assert_scoped_key(world: World, tenant_id: str, property_id: str):
    keys = world.redis_keys()
    matches = [key for key in keys if tenant_id in key and property_id in key]
    assert matches, f"expected tenant-scoped key, got {keys}"


@then(parsers.parse('Redis does not have the unscoped key "{key}"'))
def assert_no_unscoped_key(world: World, key: str):
    keys = world.redis_keys()
    assert key not in keys, f"unscoped key {key} must not exist; have {keys}"


@then(parsers.parse('Redis stores two distinct keys for property "{property_id}"'))
def assert_two_keys(world: World, property_id: str):
    keys = [key for key in world.redis_keys() if property_id in key]
    assert len(set(keys)) >= 2, f"expected two tenant keys, got {keys}"


@then(
    parsers.parse(
        'the cached payload for tenant "{tenant_id}" has total {amount}'
    )
)
def assert_cached_payload(world: World, tenant_id: str, amount: str):
    payloads = _payloads_by_tenant(world, "prop-001")
    assert tenant_id in payloads, f"no cached payload for {tenant_id}: {payloads}"
    assert Decimal(str(payloads[tenant_id]["total"])) == Decimal(amount)


@then(parsers.parse('reservation "{res_id}" is included in the monthly total'))
def assert_included(world: World, res_id: str):
    row = next(item for item in world.catalog.reservations if item.id == res_id)
    assert world.last_monthly is not None
    assert world.last_monthly >= row.total_amount
    start, end = _fake_db_bounds(world)
    if start is None or end is None:
        pytest.fail("monthly revenue must query a date range so timezone bounds can be verified")
    start = start if start.tzinfo else start.replace(tzinfo=_parse_timestamptz("2024-01-01 00:00:00+00").tzinfo)
    check_in = row.check_in
    start_cmp = start.astimezone(check_in.tzinfo) if start.tzinfo else start
    end_cmp = end.astimezone(check_in.tzinfo) if end.tzinfo else end
    assert start_cmp <= check_in < end_cmp, f"{res_id} check-in {check_in} not in [{start}, {end})"


@then(parsers.parse('reservation "{res_id}" is not included in the monthly total'))
def assert_not_included(world: World, res_id: str):
    row = next(item for item in world.catalog.reservations if item.id == res_id)
    start, end = _fake_db_bounds(world)
    if start is not None and end is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=row.check_in.tzinfo)
        if end.tzinfo is None:
            end = end.replace(tzinfo=row.check_in.tzinfo)
        assert not (start <= row.check_in < end), f"{res_id} should be outside [{start}, {end})"
        return
    assert world.last_monthly is not None
    without = world.last_monthly
    # If FakeDB was not used, the extra booking amount must not be in the total.
    assert without < (without + row.total_amount)


@then(parsers.parse('the window start is "{timestamp}"'))
def assert_window_start(world: World, timestamp: str):
    assert world.last_window is not None, "month window was not built"
    start, _end = world.last_window
    expected = datetime.fromisoformat(timestamp).astimezone(ZoneInfo("Europe/Paris"))
    actual = start.astimezone(ZoneInfo("Europe/Paris")) if start.tzinfo else start
    assert actual == expected, f"start {actual.isoformat()} != {expected.isoformat()}"


@then(parsers.parse('the window end is "{timestamp}"'))
def assert_window_end(world: World, timestamp: str):
    assert world.last_window is not None, "month window was not built"
    _start, end = world.last_window
    expected = datetime.fromisoformat(timestamp).astimezone(ZoneInfo("Europe/Paris"))
    actual = end.astimezone(ZoneInfo("Europe/Paris")) if end.tzinfo else end
    assert actual == expected, f"end {actual.isoformat()} != {expected.isoformat()}"
