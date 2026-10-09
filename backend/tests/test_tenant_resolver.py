import pytest
from app.core.tenant_resolver import TenantResolver


@pytest.mark.asyncio
async def test_unknown_user_does_not_default_to_another_tenant():
    tenant_id = await TenantResolver.resolve_tenant_id(user_id="u9", user_email="stranger@example.com")

    assert tenant_id is None
