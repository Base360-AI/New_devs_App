import asyncio
from typing import Iterable, Optional, Tuple

from .cache import invalidate_revenue_summary


async def sync_reservations(
    changed_properties: Optional[Iterable[Tuple[str, str]]] = None,
):
    await asyncio.sleep(0.1)
    for tenant_id, property_id in changed_properties or []:
        await invalidate_revenue_summary(tenant_id, property_id)
    return True
