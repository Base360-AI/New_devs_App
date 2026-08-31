from typing import Any, Dict, List

from sqlalchemy import text

from app.core.database_pool import db_pool


async def list_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """Return only properties owned by the authenticated tenant."""
    if not db_pool.session_factory:
        await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("""
                SELECT id, name, timezone
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY name, id
            """),
            {"tenant_id": tenant_id},
        )

        return [
            {
                "id": row.id,
                "name": row.name,
                "timezone": row.timezone,
            }
            for row in result.fetchall()
        ]
