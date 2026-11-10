import pytest
from jose import jwt

from app.core.tenant_resolver import TenantResolver


def _token(claims):
    return jwt.encode(claims, "test-secret", algorithm="HS256")


@pytest.mark.asyncio
async def test_unknown_user_without_tenant_gets_none():
    # Regression: this used to fall back to "tenant-a" and expose its data.
    tenant = await TenantResolver.resolve_tenant_id(
        user_id="user-x", user_email="nobody@example.test", token=_token({"email": "nobody@example.test"})
    )
    assert tenant is None


@pytest.mark.asyncio
async def test_unknown_user_without_token_gets_none():
    assert await TenantResolver.resolve_tenant_id(user_id="user-x", user_email="nobody@example.test") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("location", ["app_metadata", "user_metadata", "root"])
async def test_tenant_claim_in_token_is_used(location):
    claims = {"email": "someone@example.test"}
    if location == "root":
        claims["tenant_id"] = "tenant-b"
    else:
        claims[location] = {"tenant_id": "tenant-b"}

    tenant = await TenantResolver.resolve_tenant_id(
        user_id="user-x", user_email="someone@example.test", token=_token(claims)
    )
    assert tenant == "tenant-b"


@pytest.mark.asyncio
async def test_token_claim_wins_over_email_mapping():
    token = _token({"app_metadata": {"tenant_id": "tenant-b"}})
    tenant = await TenantResolver.resolve_tenant_id(
        user_id="user-sunset", user_email="sunset@propertyflow.com", token=token
    )
    assert tenant == "tenant-b"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "email, expected",
    [("sunset@propertyflow.com", "tenant-a"), ("ocean@propertyflow.com", "tenant-b")],
)
async def test_known_emails_still_map_without_claim(email, expected):
    assert await TenantResolver.resolve_tenant_id(user_id="u", user_email=email) == expected


@pytest.mark.asyncio
async def test_malformed_token_falls_back_to_email_mapping():
    tenant = await TenantResolver.resolve_tenant_id(
        user_id="u", user_email="ocean@propertyflow.com", token="not-a-jwt"
    )
    assert tenant == "tenant-b"
