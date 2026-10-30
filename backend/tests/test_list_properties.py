import asyncio

from app.core.database_pool import DatabasePool
from app.services.properties import list_properties


def properties_for(tenant_id: str):
    async def run():
        pool = DatabasePool()
        await pool.initialize()
        try:
            async with pool.get_session() as session:
                return await list_properties(tenant_id, db_session=session)
        finally:
            await pool.close()

    return asyncio.run(run())


def test_tenant_b_sees_only_its_properties_ordered_by_id():
    assert properties_for("tenant-b") == [
        {"id": "prop-001", "name": "Mountain Lodge Beta"},
        {"id": "prop-004", "name": "Lakeside Cottage"},
        {"id": "prop-005", "name": "Urban Loft Modern"},
    ]


def test_tenant_a_sees_only_its_properties_ordered_by_id():
    assert properties_for("tenant-a") == [
        {"id": "prop-001", "name": "Beach House Alpha"},
        {"id": "prop-002", "name": "City Apartment Downtown"},
        {"id": "prop-003", "name": "Country Villa Estate"},
    ]
