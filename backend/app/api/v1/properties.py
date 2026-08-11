from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
import logging

from ...core.auth import authenticate_request
from ...core.database_pool import DatabasePool

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/properties")
async def list_properties(
    current_user=Depends(authenticate_request),
) -> Dict[str, Any]:
    """
    List all properties belonging to the caller's tenant.
    Non-admin users only see properties in their assigned cities.
    """
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with user")

    try:
        db_pool = DatabasePool()
        await db_pool.initialize()

        if not db_pool.session_factory:
            raise Exception("Database pool not available")

        async with db_pool.get_session() as session:
            from sqlalchemy import text

            query = text("""
                SELECT *
                FROM properties
                WHERE tenant_id = :tenant_id
            """)

            result = await session.execute(query, {"tenant_id": tenant_id})
            rows = result.mappings().all()
            properties = [dict(row) for row in rows]

    except Exception as e:
        print(f"Database error fetching properties for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch properties")

    if not current_user.is_admin:
        allowed_cities = set(current_user.cities)
        properties = [
            p for p in properties
            if (p.get("city") or "").strip().lower() in allowed_cities
        ]

    logger.info(f"Returning {len(properties)} properties for tenant {tenant_id}")

    return {
        "properties": properties,
        "total": len(properties),
    }
