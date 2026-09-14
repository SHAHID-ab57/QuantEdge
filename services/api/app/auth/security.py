"""Password hashing and JWT issuance/validation.

The one place either happens on this platform. `hash_password`/
`verify_password` wrap `bcrypt` directly (no `passlib` — bcrypt's own
`hashpw`/`checkpw` are the entire API surface this needs, and `passlib`'s
own bcrypt backend has been effectively unmaintained for a while).
`create_access_token`/`decode_access_token` wrap `PyJWT`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.auth.errors import AuthNotConfiguredError, InvalidTokenError, TokenExpiredError
from app.core.config import Settings

#: bcrypt's own hard limit — enforced here as a `ValueError` with a clear
#: message rather than letting the library's own message surface
#: unhandled; `app/schemas/auth.py` also caps the field length so this is
#: normally unreachable from the API, not the only guard.
_MAX_PASSWORD_BYTES = 72

__all__ = [
    "TokenClaims",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]


@dataclass(frozen=True)
class TokenClaims:
    """The claims this platform's own tokens actually carry, decoded and
    validated — never the raw `PyJWT` payload dict past this module's own
    boundary.

    `jti` (M5-E3-T1) is a fresh random id per issued token, added
    specifically so a single token can be named and revoked — a `sub`
    (user id) alone can't do that, since one user's still-valid tokens
    from *other* sessions must not all be invalidated by one logout.
    `expires_at` lets a revocation write a Redis key with a TTL matching
    the token's own remaining lifetime, rather than guessing one or
    tracking it forever.
    """

    user_id: uuid.UUID
    jti: str
    expires_at: datetime


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt, returning a storable string.

    A fresh, random salt every call (`bcrypt.gensalt()`) — two users with
    the identical password never produce the same hash.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {_MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    Returns `False` rather than raising for an over-length password —
    the same "wrong password" outcome, not a distinguishable error, is
    correct here (see `InvalidCredentialsError`'s own docstring on why
    login never leaks which specific thing was wrong).
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))


def create_access_token(*, user_id: uuid.UUID, settings: Settings) -> str:
    """Issue a signed JWT bearer token for `user_id`.

    `sub` (the JWT-standard subject claim) carries the user's own id as a
    string — `decode_access_token` parses it back to a `UUID`. `exp` is
    set from `settings.jwt_access_token_expire_minutes`. `jti` (M5-E3-T1)
    is a fresh `uuid4` per token, naming this one issuance so it alone —
    not every token this user has ever been issued — can be revoked.
    """
    if not settings.jwt_secret_key:
        raise AuthNotConfiguredError()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, *, settings: Settings) -> TokenClaims:
    """Validate a bearer token and return the claims it carries.

    Raises `TokenExpiredError` for an expired-but-otherwise-valid token,
    `InvalidTokenError` for anything else wrong (bad signature, malformed
    payload, missing/malformed `sub` or `jti`) — never a raw
    `jwt`-library exception past this boundary. Does **not** check
    whether the token has been revoked — that's `app.auth
    .token_revocation.TokenBlocklist`'s own job, checked separately by
    `get_current_user`, since revocation needs an async store lookup this
    module has no business knowing about.
    """
    if not settings.jwt_secret_key:
        raise AuthNotConfiguredError()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError() from exc

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise InvalidTokenError("Token is missing its subject claim")
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise InvalidTokenError("Token subject is not a valid user id") from exc

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise InvalidTokenError("Token is missing its jti claim")

    expires_at_ts = payload.get("exp")
    if not isinstance(expires_at_ts, int | float):
        raise InvalidTokenError("Token is missing its exp claim")

    return TokenClaims(
        user_id=user_id, jti=jti, expires_at=datetime.fromtimestamp(expires_at_ts, tz=UTC)
    )
