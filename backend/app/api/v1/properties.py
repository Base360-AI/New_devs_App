from fastapi import APIRouter, Depends
from typing import List, Dict, Any
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/properties")
async def get_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None) or "default_tenant"

    from app.core.database_pool import db_pool
    from sqlalchemy import text

    if not db_pool.session_factory:
        await db_pool.initialize()

    async with db_pool.get_session() as session:
        query = text("""
            SELECT id, name, timezone
            FROM properties
            WHERE tenant_id = :tenant_id
            ORDER BY name
        """)
        result = await session.execute(query, {"tenant_id": tenant_id})
        rows = result.fetchall()

    items = [{"id": row.id, "name": row.name, "timezone": row.timezone} for row in rows]
    return {"data": items, "total": len(items)}
