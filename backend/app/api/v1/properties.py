from fastapi import APIRouter, Depends
from typing import Dict, Any

from sqlalchemy import text

from app.core.auth import authenticate_request as get_current_user
from app.core.database_pool import db_pool

router = APIRouter()

# Scoped to the caller's tenant: property names alone disclose a client's portfolio,
# so the list is never assembled anywhere the tenant is unknown.
_TENANT_PROPERTIES_SQL = text("""
    SELECT id, name, timezone
    FROM properties
    WHERE tenant_id = :tenant_id
    ORDER BY name
""")


@router.get("/properties")
async def list_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        result = await session.execute(
            _TENANT_PROPERTIES_SQL, {"tenant_id": tenant_id}
        )
        rows = result.fetchall()

    # Paginated {items, total} shape, matching what SecureAPI.getProperties already
    # normalises and what the other list endpoints in this API return.
    items = [
        {"id": row.id, "name": row.name, "timezone": row.timezone}
        for row in rows
    ]

    return {"items": items, "total": len(items)}
