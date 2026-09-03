from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List
import logging
from app.services.cache import get_revenue_summary
from app.services.reservations import get_tenant_properties, PropertyNotFoundError, MixedCurrencyError
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: int = 2024,
    month: int = 3,
    current_user: Any = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id or tenant_id == "default_tenant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a valid tenant"
        )

    try:
        revenue_data = await get_revenue_summary(
            property_id=property_id,
            tenant_id=tenant_id,
            year=year,
            month=month
        )
    except PropertyNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except MixedCurrencyError as e:
        logger.error(f"Mixed currency error for property {property_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error calculating revenue summary for property {property_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate revenue summary"
        )

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(revenue_data['total']),
        "currency": revenue_data.get('currency', 'USD'),
        "reservations_count": revenue_data.get('count', 0),
        "year": revenue_data.get('year', year),
        "month": revenue_data.get('month', month)
    }

@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: Any = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id or tenant_id == "default_tenant":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not associated with a valid tenant"
        )

    return await get_tenant_properties(tenant_id)
