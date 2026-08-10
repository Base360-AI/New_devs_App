from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import RevenueUnavailableError
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=1970, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    # No "default_tenant" fallback: a request we cannot attribute to a tenant must
    # not be answered with data, otherwise every unattributed user shares one bucket.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant associated with this account",
        )

    if (month is None) != (year is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month and year must be supplied together",
        )

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    except RevenueUnavailableError as exc:
        # Never fall back to placeholder figures - a wrong number on a finance
        # dashboard is worse than a visible error.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Revenue is temporarily unavailable: {exc}",
        )

    return {
        "property_id": revenue_data['property_id'],
        # Sent as a decimal string. float() on a NUMERIC(10,3) total silently
        # rebinds the value to the nearest IEEE-754 double, which is where the
        # "a few cents off" reports came from.
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "timezone": revenue_data.get('timezone'),
        "period": {"month": month, "year": year} if month and year else None,
    }
