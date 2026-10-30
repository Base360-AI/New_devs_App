from typing import Any, Dict, List


async def list_properties(tenant_id: str, db_session=None) -> List[Dict[str, Any]]:
    """
    Returns the properties that belong to one tenant, ordered by id.
    """
    from sqlalchemy import text

    query = text("""
        SELECT id, name
        FROM properties
        WHERE tenant_id = :tenant_id
        ORDER BY id
    """)
    params = {"tenant_id": tenant_id}

    if db_session is None:
        from app.core.database_pool import db_pool

        if not db_pool.session_factory:
            await db_pool.initialize()
        async with db_pool.get_session() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()
    else:
        result = await db_session.execute(query, params)
        rows = result.fetchall()

    return [{"id": row.id, "name": row.name} for row in rows]
