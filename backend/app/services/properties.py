from typing import Dict, Any, List


async def list_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Return the properties that belong to a single tenant.

    Tenant-scoped on purpose: property IDs are only unique within a tenant
    (database/schema.sql: PRIMARY KEY (id, tenant_id)), so the list MUST be
    filtered by tenant_id. On any DB error we return an empty list rather than
    falling back to shared/hardcoded data -- showing one tenant another tenant's
    property names is the same class of privacy leak we just fixed.
    """
    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()
        if not db_pool.session_factory:
            raise Exception("Database pool not available")

        async with db_pool.get_session() as session:
            result = await session.execute(
                text(
                    "SELECT id, name, timezone FROM properties "
                    "WHERE tenant_id = :tenant_id ORDER BY id"
                ),
                {"tenant_id": tenant_id},
            )
            return [
                {"id": row.id, "name": row.name, "timezone": row.timezone}
                for row in result.fetchall()
            ]
    except Exception as e:
        print(f"Error listing properties for tenant {tenant_id}: {e}")
        return []
