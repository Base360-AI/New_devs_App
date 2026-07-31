import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_calculate_total_revenue_never_hits_mock_fallback():
    """
    When database pool is properly initialized, calculate_total_revenue
    queries the database and does NOT fall back to mock data.
    """
    print_calls = []

    def capture(*args, **kwargs):
        msg = args[0] if args else ""
        if isinstance(msg, str):
            print_calls.append(msg)

    from app.core.database_pool import db_pool

    mock_row = MagicMock()
    mock_row.total_revenue = Decimal("2250.000")
    mock_row.reservation_count = 4

    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__.return_value = mock_session

    mock_factory = MagicMock(return_value=mock_session)

    try:
        with patch(
            "app.core.database_pool.async_sessionmaker", return_value=mock_factory
        ):
            await db_pool.initialize()

        with patch("builtins.print", capture):
            from app.services.reservations import calculate_total_revenue

            result = await calculate_total_revenue("prop-001", "tenant-a")

        errors = [c for c in print_calls if "Database error" in c]
        assert not errors, f"Encountered database error: {errors[0]}"
        assert result["total"] == "2250.00"
        assert result["count"] == 4
    finally:
        db_pool.session_factory = None
        db_pool.engine = None