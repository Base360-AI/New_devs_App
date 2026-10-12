from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import RevenueDataUnavailable
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

CENTS = Decimal("0.01")


def to_currency_string(amount: str) -> str:
    """
    Rounds an exact amount to cents and renders it as a string.

    reservations.total_amount is NUMERIC(10,3), so a total can land on a half
    cent. Going through float to do that rounding resolves half cents
    downwards -- 0.005 becomes 0.00 rather than 0.01 -- because the binary
    value sits just below the midpoint. Rounding the Decimal explicitly makes
    the policy half-up, and sending a string keeps JSON parsing from putting
    the result back into a float.
    """
    return str(Decimal(amount).quantize(CENTS, rounding=ROUND_HALF_UP))

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        # Without a known tenant there is no safe row set to return. The old
        # "default_tenant" fallback resolved to real data belonging to someone.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant is associated with this account",
        )
    
    if (month is None) != (year is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month and year must be supplied together",
        )
    
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except RevenueDataUnavailable as e:
        # Report the outage. A dashboard that quietly shows a stand-in figure
        # is worse than one that admits it cannot answer.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue data is temporarily unavailable",
        ) from e
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": to_currency_string(revenue_data['total']),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
