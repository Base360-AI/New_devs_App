from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from sqlalchemy import text
from app.core.auth import authenticate_request as get_current_user
from app.core.database_pool import DatabasePool

router = APIRouter()

@router.get("/properties")
async def list_properties(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    db_pool = DatabasePool()
    await db_pool.initialize()

    async with await db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name FROM properties WHERE tenant_id = :tenant_id ORDER BY name"),
            {"tenant_id": tenant_id}
        )
        return [{"id": row.id, "name": row.name} for row in result.fetchall()]
