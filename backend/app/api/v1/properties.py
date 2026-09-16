"""
Properties API — the tenant's own property list.

The dashboard's property selector used to be a hardcoded array in the frontend,
identical for every user, so each client was offered the other client's
properties (and the duplicated id prop-001 collapsed into a single entry under
the wrong name). The list has to come from the database, scoped to the caller's
tenant.
"""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from ...core.auth import authenticate_request
from ...core.database_pool import db_pool
from ...models.auth import AuthenticatedUser

import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["properties"])


@router.get("/properties")
async def list_properties(
    current_user: AuthenticatedUser = Depends(authenticate_request),
) -> List[Dict[str, Any]]:
    """Return the properties belonging to the caller's tenant."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this account")

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT id, name, timezone
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY id
                """
            ),
            {"tenant_id": tenant_id},
        )
        rows = result.fetchall()

    logger.info("Listed %d properties for tenant %s", len(rows), tenant_id)
    return [
        {"id": row.id, "name": row.name, "timezone": row.timezone} for row in rows
    ]
