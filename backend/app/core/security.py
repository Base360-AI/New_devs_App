"""Small authentication primitives used by the interview application.

The application deliberately keeps its two supplied demo accounts local, but
does not keep their passwords in executable code or accept unsigned tokens.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import time
from typing import Deque, Dict, Optional, Tuple
from uuid import uuid4

import jwt

from ..config import settings


JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = "propertyflow-web"
JWT_ISSUER = "propertyflow-api"
ACCESS_TOKEN_TTL = timedelta(hours=1)
PASSWORD_ITERATIONS = 310_000


@dataclass(frozen=True)
class LocalUser:
    id: str
    email: str
    name: str
    tenant_id: str
    password_salt: str
    password_hash: str
    role: str = "user"


# PBKDF2-SHA256 hashes for the two credentials published in ASSIGNMENT.md.
# Keeping hashes here preserves the debugging exercise without embedding
# plaintext passwords in the authentication implementation.
LOCAL_USERS: Dict[str, LocalUser] = {
    "sunset@propertyflow.com": LocalUser(
        id="user-sunset",
        email="sunset@propertyflow.com",
        name="Sunset Properties Manager",
        tenant_id="tenant-a",
        password_salt="9e5aef1feaf82803cf1d27c722f1e86f",
        password_hash="cf12d62b890df4a933a82ef31cbd1bb6fd8894cfb238f458f330a693d84c35ed",
    ),
    "ocean@propertyflow.com": LocalUser(
        id="user-ocean",
        email="ocean@propertyflow.com",
        name="Ocean Rentals Manager",
        tenant_id="tenant-b",
        password_salt="d8a023a6da044e7dbf3f3aabbce06af0",
        password_hash="e334f897374d44cbc21958866e7e040e9021b571c4f412237a32cbb2256ad1e9",
    ),
}

_DUMMY_SALT = bytes.fromhex("00000000000000000000000000000000")
_DUMMY_HASH = hashlib.pbkdf2_hmac(
    "sha256", b"invalid-password", _DUMMY_SALT, PASSWORD_ITERATIONS
)


def authenticate_local_user(email: str, password: str) -> Optional[LocalUser]:
    """Return a local demo user only after constant-time password verification."""
    normalized_email = email.lower().strip()
    user = LOCAL_USERS.get(normalized_email)
    salt = bytes.fromhex(user.password_salt) if user else _DUMMY_SALT
    expected = bytes.fromhex(user.password_hash) if user else _DUMMY_HASH
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    if user and hmac.compare_digest(candidate, expected):
        return user
    return None


def create_access_token(user: LocalUser) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "id": user.id,  # Kept while older application code migrates to `sub`.
        "email": user.email,
        "tenant_id": user.tenant_id,
        "app_metadata": {"role": user.role, "tenant_id": user.tenant_id},
        "user_metadata": {"name": user.name},
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + ACCESS_TOKEN_TTL,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Validate signature and all identity/lifetime claims for a local token."""
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[JWT_ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={
            "require": ["sub", "email", "tenant_id", "iss", "aud", "iat", "nbf", "exp", "jti"]
        },
    )


class LoginRateLimiter:
    """Process-local sliding-window protection suitable for this demo service."""

    def __init__(self, max_failures: int = 5, window_seconds: int = 60):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    def _key(self, email: str, client_ip: str) -> Tuple[str, str]:
        return email.lower().strip(), client_ip or "unknown"

    def _active_failures(self, key: Tuple[str, str], now: float) -> Deque[float]:
        failures = self._failures[key]
        cutoff = now - self.window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures

    def is_blocked(self, email: str, client_ip: str, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else now
        return len(self._active_failures(self._key(email, client_ip), current)) >= self.max_failures

    def record_failure(self, email: str, client_ip: str, now: Optional[float] = None) -> None:
        current = time.monotonic() if now is None else now
        self._active_failures(self._key(email, client_ip), current).append(current)

    def record_success(self, email: str, client_ip: str) -> None:
        self._failures.pop(self._key(email, client_ip), None)

    def clear(self) -> None:
        self._failures.clear()


login_rate_limiter = LoginRateLimiter()

# Local JWT logout support. This is intentionally process-local like the rest
# of the interview authentication stub; a production identity provider would
# own revocation centrally.
_revoked_tokens: Dict[str, float] = {}


def revoke_access_token(payload: dict) -> None:
    jti = payload.get("jti")
    expires_at = payload.get("exp")
    if jti and expires_at:
        _revoked_tokens[str(jti)] = float(expires_at)


def is_access_token_revoked(payload: dict) -> bool:
    now = datetime.now(timezone.utc).timestamp()
    expired = [jti for jti, expires_at in _revoked_tokens.items() if expires_at <= now]
    for jti in expired:
        _revoked_tokens.pop(jti, None)
    return str(payload.get("jti")) in _revoked_tokens
