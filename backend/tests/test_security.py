import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
from fastapi import HTTPException

from app.config import settings
from app.core.security import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    LoginRateLimiter,
    authenticate_local_user,
    create_access_token,
    decode_access_token,
)
from app.core.tenant_access import require_user_in_operator_tenant
from app.models.auth import AuthenticatedUser


class LocalAuthenticationTests(unittest.TestCase):
    def test_known_demo_password_is_verified(self) -> None:
        user = authenticate_local_user(" SUNSET@propertyflow.com ", "client_a_2024")
        self.assertIsNotNone(user)
        self.assertEqual(user.tenant_id, "tenant-a")

    def test_wrong_password_and_unknown_user_are_rejected(self) -> None:
        self.assertIsNone(
            authenticate_local_user("sunset@propertyflow.com", "definitely-wrong")
        )
        self.assertIsNone(
            authenticate_local_user("candidate@propertyflow.com", "anything")
        )

    def test_local_token_requires_signature_and_security_claims(self) -> None:
        user = authenticate_local_user("ocean@propertyflow.com", "client_b_2024")
        payload = decode_access_token(create_access_token(user))
        self.assertEqual(payload["tenant_id"], "tenant-b")
        self.assertEqual(payload["iss"], JWT_ISSUER)

        unsigned = jwt.encode(
            {
                "sub": "attacker",
                "email": "candidate@propertyflow.com",
                "tenant_id": "tenant-a",
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "iat": datetime.now(timezone.utc),
                "nbf": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
                "jti": "forged",
            },
            key="",
            algorithm="none",
        )
        with self.assertRaises(jwt.InvalidTokenError):
            decode_access_token(unsigned)

    def test_expired_token_is_rejected(self) -> None:
        now = datetime.now(timezone.utc)
        expired = jwt.encode(
            {
                "sub": "user-sunset",
                "email": "sunset@propertyflow.com",
                "tenant_id": "tenant-a",
                "iss": JWT_ISSUER,
                "aud": JWT_AUDIENCE,
                "iat": now - timedelta(hours=2),
                "nbf": now - timedelta(hours=2),
                "exp": now - timedelta(hours=1),
                "jti": "expired",
            },
            settings.secret_key,
            algorithm=JWT_ALGORITHM,
        )
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_access_token(expired)

    def test_rate_limiter_blocks_after_repeated_failures(self) -> None:
        limiter = LoginRateLimiter(max_failures=2, window_seconds=60)
        limiter.record_failure("a@example.com", "127.0.0.1", now=1)
        self.assertFalse(limiter.is_blocked("a@example.com", "127.0.0.1", now=2))
        limiter.record_failure("a@example.com", "127.0.0.1", now=3)
        self.assertTrue(limiter.is_blocked("a@example.com", "127.0.0.1", now=4))
        limiter.record_success("a@example.com", "127.0.0.1")
        self.assertFalse(limiter.is_blocked("a@example.com", "127.0.0.1", now=5))


class _MembershipQuery:
    def __init__(self, allowed: bool):
        self.allowed = allowed

    def table(self, *_args):
        return self

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return type("Response", (), {"data": [{"tenant_id": "tenant-a"}] if self.allowed else []})()

    @property
    def service(self):
        return self


class TenantAccessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.operator = AuthenticatedUser(
            id="operator",
            email="operator@example.com",
            permissions=[],
            cities=[],
            is_admin=True,
            tenant_id="tenant-a",
        )

    def test_same_tenant_target_is_allowed(self) -> None:
        with patch("app.core.tenant_access.supabase", _MembershipQuery(True)):
            self.assertEqual(
                require_user_in_operator_tenant(self.operator, "target"), "tenant-a"
            )

    def test_cross_tenant_target_is_hidden(self) -> None:
        with patch("app.core.tenant_access.supabase", _MembershipQuery(False)):
            with self.assertRaises(HTTPException) as context:
                require_user_in_operator_tenant(self.operator, "tenant-b-user")
        self.assertEqual(context.exception.status_code, 404)


class RouteSecurityTests(unittest.TestCase):
    def test_only_liveness_and_login_routes_are_public(self) -> None:
        from app.main import app

        public_operations = set()
        for path, path_item in app.openapi()["paths"].items():
            for method, operation in path_item.items():
                if method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}:
                    continue
                if not operation.get("security"):
                    public_operations.add((method.upper(), path))

        self.assertEqual(
            public_operations,
            {
                ("POST", "/api/v1/auth/login"),
                ("GET", "/health"),
                ("HEAD", "/health"),
                ("GET", "/up"),
                ("GET", "/api/v1/health"),
                ("HEAD", "/api/v1/health"),
                ("GET", "/api/v1/up"),
            },
        )


if __name__ == "__main__":
    unittest.main()
