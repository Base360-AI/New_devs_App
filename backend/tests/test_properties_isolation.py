import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.mark.asyncio
async def test_properties_returned_only_for_correct_tenant():
    """
    get_tenant_properties_db must return only the calling tenant's
    properties, even when property IDs overlap across tenants.
    """
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session

    def _row(id, name, timezone, tenant_id):
        r = MagicMock()
        r.id = id
        r.name = name
        r.timezone = timezone
        r.tenant_id = tenant_id
        return r

    tenant_a_props = [
        _row("prop-001", "Beach House Alpha", "Europe/Paris", "tenant-a"),
        _row("prop-002", "City Apartment Downtown", "Europe/Paris", "tenant-a"),
        _row("prop-003", "Country Villa Estate", "Europe/Paris", "tenant-a"),
    ]
    tenant_b_props = [
        _row("prop-001", "Mountain Lodge Beta", "America/New_York", "tenant-b"),
        _row("prop-004", "Lakeside Cottage", "America/New_York", "tenant-b"),
        _row("prop-005", "Urban Loft Modern", "America/New_York", "tenant-b"),
    ]

    executed_params = []

    async def mock_execute(query, params):
        executed_params.append(dict(params))
        result = MagicMock()
        if params["tenant_id"] == "tenant-a":
            result.fetchall.return_value = tenant_a_props
        else:
            result.fetchall.return_value = tenant_b_props
        return result

    mock_session.execute = mock_execute

    mock_factory = MagicMock(return_value=mock_session)

    from app.core.database_pool import db_pool

    try:
        with patch(
            "app.core.database_pool.async_sessionmaker", return_value=mock_factory
        ):
            await db_pool.initialize()

        from app.services.properties import get_tenant_properties_db

        a_result = await get_tenant_properties_db("tenant-a")
        b_result = await get_tenant_properties_db("tenant-b")

        # tenant-a: has prop-001 (Beach House Alpha), not prop-004 or prop-005
        a_ids = [p["id"] for p in a_result]
        assert "prop-001" in a_ids
        assert "prop-002" in a_ids
        assert "prop-003" in a_ids
        assert "prop-004" not in a_ids
        assert "prop-005" not in a_ids
        assert a_result[0]["name"] == "Beach House Alpha"

        # tenant-b: has prop-001 (Mountain Lodge Beta), not prop-002 or prop-003
        b_ids = [p["id"] for p in b_result]
        assert "prop-001" in b_ids
        assert "prop-004" in b_ids
        assert "prop-005" in b_ids
        assert "prop-002" not in b_ids
        assert "prop-003" not in b_ids
        assert b_result[0]["name"] == "Mountain Lodge Beta"

        # Both queries include tenant_id in params
        assert executed_params[0]["tenant_id"] == "tenant-a"
        assert executed_params[1]["tenant_id"] == "tenant-b"

    finally:
        db_pool.session_factory = None
        db_pool.engine = None