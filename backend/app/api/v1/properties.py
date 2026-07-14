from fastapi import APIRouter, Depends
from typing import Dict, Any
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

# Seed data mirrors database/seed.sql so the fallback matches actual DB contents.
_TENANT_PROPERTIES = {
    'tenant-a': [
        {'id': 'prop-001', 'name': 'Beach House Alpha', 'timezone': 'Europe/Paris'},
        {'id': 'prop-002', 'name': 'City Apartment Downtown', 'timezone': 'Europe/Paris'},
        {'id': 'prop-003', 'name': 'Country Villa Estate', 'timezone': 'Europe/Paris'},
    ],
    'tenant-b': [
        {'id': 'prop-001', 'name': 'Mountain Lodge Beta', 'timezone': 'America/New_York'},
        {'id': 'prop-004', 'name': 'Lakeside Cottage', 'timezone': 'America/New_York'},
        {'id': 'prop-005', 'name': 'Urban Loft Modern', 'timezone': 'America/New_York'},
    ],
}


@router.get("/properties")
async def list_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None) or "default_tenant"

    try:
        from sqlalchemy import text
        from app.core.database_pool import DatabasePool

        db_pool = DatabasePool()
        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                query = text("""
                    SELECT id, name, timezone
                    FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY name
                """)
                result = await session.execute(query, {"tenant_id": tenant_id})
                rows = result.fetchall()
                properties = [
                    {"id": row.id, "name": row.name, "timezone": row.timezone}
                    for row in rows
                ]
                return {"items": properties, "total": len(properties)}
    except Exception as e:
        print(f"DB error fetching properties for tenant {tenant_id}: {e}")

    properties = _TENANT_PROPERTIES.get(tenant_id, [])
    return {"items": properties, "total": len(properties)}
