"""Password hashing and JWT issuance/validation.

The one place either happens on this platform. `hash_password`/
`verify_password` wrap `bcrypt` directly (no `passlib` — bcrypt's own
`hashpw`/`checkpw` are the entire API surface this needs, and `passlib`'s
own bcrypt backend has been effectively unmaintained for a while).
`create_access_token`/`decode_access_token` wrap `PyJWT`.
"""

import uuid
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
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]


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
    set from `settings.jwt_access_token_expire_minutes`.
    """
    if not settings.jwt_secret_key:
        raise AuthNotConfiguredError()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, *, settings: Settings) -> uuid.UUID:
    """Validate a bearer token and return the user id it names.

    Raises `TokenExpiredError` for an expired-but-otherwise-valid token,
    `InvalidTokenError` for anything else wrong (bad signature, malformed
    payload, missing/malformed `sub`) — never a raw `jwt`-library
    exception past this boundary.
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
        return uuid.UUID(subject)
    except ValueError as exc:
        raise InvalidTokenError("Token subject is not a valid user id") from exc
