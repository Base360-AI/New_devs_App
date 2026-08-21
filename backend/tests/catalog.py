"""In-memory copy of database/seed.sql for isolation and timezone tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Optional


UTC = timezone.utc


def _parse_timestamptz(value: str) -> datetime:
    """Parse seed timestamps like '2024-02-29 23:30:00+00'."""
    return datetime.fromisoformat(value.replace(" ", "T")).astimezone(UTC)


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass(frozen=True)
class Property:
    id: str
    tenant_id: str
    name: str
    timezone: str


@dataclass
class Reservation:
    id: str
    property_id: str
    tenant_id: str
    check_in: datetime
    check_out: datetime
    total_amount: Decimal


@dataclass
class ReservationCatalog:
    properties: list[Property] = field(default_factory=list)
    reservations: list[Reservation] = field(default_factory=list)

    @classmethod
    def seed(cls) -> "ReservationCatalog":
        catalog = cls(
            properties=[
                Property("prop-001", "tenant-a", "Beach House Alpha", "Europe/Paris"),
                Property("prop-001", "tenant-b", "Mountain Lodge Beta", "America/New_York"),
                Property("prop-002", "tenant-a", "City Apartment Downtown", "Europe/Paris"),
                Property("prop-003", "tenant-a", "Country Villa Estate", "Europe/Paris"),
                Property("prop-004", "tenant-b", "Lakeside Cottage", "America/New_York"),
                Property("prop-005", "tenant-b", "Urban Loft Modern", "America/New_York"),
            ],
            reservations=[
                Reservation(
                    "res-tz-1",
                    "prop-001",
                    "tenant-a",
                    _parse_timestamptz("2024-02-29 23:30:00+00"),
                    _parse_timestamptz("2024-03-05 10:00:00+00"),
                    Decimal("1250.000"),
                ),
                Reservation(
                    "res-dec-1",
                    "prop-001",
                    "tenant-a",
                    _parse_timestamptz("2024-03-15 10:00:00+00"),
                    _parse_timestamptz("2024-03-18 10:00:00+00"),
                    Decimal("333.333"),
                ),
                Reservation(
                    "res-dec-2",
                    "prop-001",
                    "tenant-a",
                    _parse_timestamptz("2024-03-16 10:00:00+00"),
                    _parse_timestamptz("2024-03-19 10:00:00+00"),
                    Decimal("333.333"),
                ),
                Reservation(
                    "res-dec-3",
                    "prop-001",
                    "tenant-a",
                    _parse_timestamptz("2024-03-17 10:00:00+00"),
                    _parse_timestamptz("2024-03-20 10:00:00+00"),
                    Decimal("333.334"),
                ),
                Reservation(
                    "res-004",
                    "prop-002",
                    "tenant-a",
                    _parse_timestamptz("2024-03-05 14:00:00+00"),
                    _parse_timestamptz("2024-03-08 11:00:00+00"),
                    Decimal("1250.00"),
                ),
                Reservation(
                    "res-005",
                    "prop-002",
                    "tenant-a",
                    _parse_timestamptz("2024-03-12 16:00:00+00"),
                    _parse_timestamptz("2024-03-15 10:00:00+00"),
                    Decimal("1475.50"),
                ),
                Reservation(
                    "res-006",
                    "prop-002",
                    "tenant-a",
                    _parse_timestamptz("2024-03-20 15:00:00+00"),
                    _parse_timestamptz("2024-03-23 12:00:00+00"),
                    Decimal("1199.25"),
                ),
                Reservation(
                    "res-007",
                    "prop-002",
                    "tenant-a",
                    _parse_timestamptz("2024-03-25 18:00:00+00"),
                    _parse_timestamptz("2024-03-28 14:00:00+00"),
                    Decimal("1050.75"),
                ),
                Reservation(
                    "res-008",
                    "prop-003",
                    "tenant-a",
                    _parse_timestamptz("2024-03-02 15:00:00+00"),
                    _parse_timestamptz("2024-03-09 12:00:00+00"),
                    Decimal("2850.00"),
                ),
                Reservation(
                    "res-009",
                    "prop-003",
                    "tenant-a",
                    _parse_timestamptz("2024-03-18 16:00:00+00"),
                    _parse_timestamptz("2024-03-25 11:00:00+00"),
                    Decimal("3250.50"),
                ),
                Reservation(
                    "res-010",
                    "prop-004",
                    "tenant-b",
                    _parse_timestamptz("2024-03-08 18:00:00+00"),
                    _parse_timestamptz("2024-03-11 15:00:00+00"),
                    Decimal("420.00"),
                ),
                Reservation(
                    "res-011",
                    "prop-004",
                    "tenant-b",
                    _parse_timestamptz("2024-03-14 17:00:00+00"),
                    _parse_timestamptz("2024-03-18 14:00:00+00"),
                    Decimal("560.75"),
                ),
                Reservation(
                    "res-012",
                    "prop-004",
                    "tenant-b",
                    _parse_timestamptz("2024-03-22 16:00:00+00"),
                    _parse_timestamptz("2024-03-26 13:00:00+00"),
                    Decimal("480.25"),
                ),
                Reservation(
                    "res-013",
                    "prop-004",
                    "tenant-b",
                    _parse_timestamptz("2024-03-28 19:00:00+00"),
                    _parse_timestamptz("2024-03-31 15:00:00+00"),
                    Decimal("315.50"),
                ),
                Reservation(
                    "res-014",
                    "prop-005",
                    "tenant-b",
                    _parse_timestamptz("2024-03-06 19:00:00+00"),
                    _parse_timestamptz("2024-03-10 16:00:00+00"),
                    Decimal("920.00"),
                ),
                Reservation(
                    "res-015",
                    "prop-005",
                    "tenant-b",
                    _parse_timestamptz("2024-03-15 18:00:00+00"),
                    _parse_timestamptz("2024-03-19 17:00:00+00"),
                    Decimal("1080.40"),
                ),
                Reservation(
                    "res-016",
                    "prop-005",
                    "tenant-b",
                    _parse_timestamptz("2024-03-24 20:00:00+00"),
                    _parse_timestamptz("2024-03-29 14:00:00+00"),
                    Decimal("1255.60"),
                ),
            ],
        )
        return catalog

    def timezone_for(self, property_id: str, tenant_id: str) -> str:
        for prop in self.properties:
            if prop.id == property_id and prop.tenant_id == tenant_id:
                return prop.timezone
        raise KeyError(f"Unknown property {property_id} for {tenant_id}")

    def lifetime_total(self, property_id: str, tenant_id: str) -> tuple[Decimal, int]:
        rows = [
            row
            for row in self.reservations
            if row.property_id == property_id and row.tenant_id == tenant_id
        ]
        total = sum((row.total_amount for row in rows), Decimal("0.000"))
        return total, len(rows)

    def query(
        self,
        property_id: str,
        tenant_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> tuple[Decimal, int]:
        if start is None or end is None:
            return self.lifetime_total(property_id, tenant_id)
        start_utc = _as_aware(start)
        end_utc = _as_aware(end)
        matched = [
            row
            for row in self.reservations
            if row.property_id == property_id
            and row.tenant_id == tenant_id
            and start_utc <= _as_aware(row.check_in) < end_utc
        ]
        total = sum((row.total_amount for row in matched), Decimal("0.000"))
        return total, len(matched)

    def total_in_range(
        self,
        property_id: str,
        tenant_id: str,
        start: datetime,
        end: datetime,
    ) -> Decimal:
        total, _count = self.query(property_id, tenant_id, start, end)
        return total

    def add_reservation(
        self,
        reservation_id: str,
        property_id: str,
        tenant_id: str,
        check_in: str,
        check_out: str,
        amount: str,
    ) -> None:
        self.reservations.append(
            Reservation(
                reservation_id,
                property_id,
                tenant_id,
                _parse_timestamptz(check_in),
                _parse_timestamptz(check_out),
                Decimal(amount),
            )
        )


class _FakeResult:
    def __init__(self, total: Decimal, count: int):
        self._total = total
        self._count = count

    def fetchone(self):
        return type(
            "Row",
            (),
            {"total_revenue": self._total, "reservation_count": self._count},
        )()


class FakeDB:
    """Stand-in session for calculate_monthly_revenue / calculate_total_revenue.

    Production code can call either fetch_val(query, *args) or execute(query, params).
    Bounds are applied as-is so naive UTC windows fail the timezone scenarios.
    """

    def __init__(self, catalog: ReservationCatalog):
        self.catalog = catalog
        self.last_sql: str = ""
        self.last_params: Any = None

    async def __aenter__(self) -> "FakeDB":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def property_timezone(self, property_id: str, tenant_id: str) -> str:
        return self.catalog.timezone_for(property_id, tenant_id)

    def _record(self, query: Any, params: Any) -> None:
        self.last_sql = str(query)
        self.last_params = params

    def _query_from_args(self, args: Iterable[Any]) -> tuple[Decimal, int]:
        values = list(args)
        property_id, tenant_id, start, end = values[0], values[1], values[2], values[3]
        return self.catalog.query(property_id, tenant_id, start, end)

    def _query_from_params(self, params: dict[str, Any]) -> tuple[Decimal, int]:
        tenant_id = params.get("tenant_id")
        if not tenant_id:
            raise AssertionError("Query params must include tenant_id for virtual isolation")
        start = params.get("start_date") or params.get("start")
        end = params.get("end_date") or params.get("end")
        property_id = params["property_id"]
        return self.catalog.query(property_id, tenant_id, start, end)

    async def fetch_val(self, query: Any, *args: Any) -> Decimal:
        self._record(query, args)
        if len(args) < 4:
            raise AssertionError(
                "fetch_val must bind property_id, tenant_id, start_date, end_date"
            )
        total, _count = self._query_from_args(args)
        return total

    async def execute(self, query: Any, params: Optional[dict[str, Any]] = None):
        self._record(query, params)
        if not isinstance(params, dict):
            raise AssertionError("execute() must bind a params dict that includes tenant_id")
        total, count = self._query_from_params(params)
        return _FakeResult(total, count)
