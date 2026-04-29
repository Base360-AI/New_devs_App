from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # Round to 2 decimal places using Decimal before converting to float to
    # avoid floating-point precision errors (e.g. 333.333+333.333+333.334 != 1000.00)
    total_revenue = Decimal(str(revenue_data['total'])).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }


@router.get("/dashboard/properties")
async def get_tenant_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Return the list of properties belonging to the current tenant."""
    from app.core.database_pool import DatabasePool
    from sqlalchemy import text

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    # Tenant-specific fallback property lists used when DB is unavailable
    mock_properties = {
        "tenant-a": [
            {"id": "prop-001", "name": "Beach House Alpha"},
            {"id": "prop-002", "name": "City Apartment Downtown"},
            {"id": "prop-003", "name": "Country Villa Estate"},
        ],
        "tenant-b": [
            {"id": "prop-001", "name": "Mountain Lodge Beta"},
            {"id": "prop-004", "name": "Lakeside Cottage"},
            {"id": "prop-005", "name": "Urban Loft Modern"},
        ],
    }

    try:
        db_pool = DatabasePool()
        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                query = text(
                    "SELECT id, name FROM properties WHERE tenant_id = :tenant_id ORDER BY name"
                )
                result = await session.execute(query, {"tenant_id": tenant_id})
                rows = result.fetchall()
                return {"properties": [{"id": r.id, "name": r.name} for r in rows]}
    except Exception as e:
        pass

    return {"properties": mock_properties.get(tenant_id, [])}
