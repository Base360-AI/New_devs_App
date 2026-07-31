from typing import List, Dict, Any


async def get_tenant_properties_db(tenant_id: str) -> List[Dict[str, Any]]:
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                "SELECT id, name, timezone, tenant_id "
                "FROM properties "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        )
        rows = result.fetchall()
        return [
            {
                "id": row.id,
                "name": row.name,
                "timezone": row.timezone,
                "tenant_id": row.tenant_id,
            }
            for row in rows
        ]