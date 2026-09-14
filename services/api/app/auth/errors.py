"""Domain errors for authentication."""

from fastapi import status

from app.core.exceptions import AppError


class InvalidCredentialsError(AppError):
    """Raised for a login with an unknown email or a wrong password.

    Deliberately the *same* error, with the *same* message, for both
    causes — a login endpoint that says "no such user" for one and
    "wrong password" for the other hands an attacker a free username
    enumeration oracle. Nothing about which one was wrong is ever
    revealed.
    """

    def __init__(self) -> None:
        super().__init__(
            "Invalid email or password",
            code="invalid_credentials",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class MissingCredentialsError(AppError):
    """Raised when a protected route is called with no bearer token at all."""

    def __init__(self) -> None:
        super().__init__(
            "Authentication required",
            code="authentication_required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class InvalidTokenError(AppError):
    """Raised for a bearer token that is malformed, has a bad signature, or
    whose subject no longer resolves to a real user."""

    def __init__(self, detail: str = "Invalid authentication token") -> None:
        super().__init__(
            detail,
            code="invalid_token",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class TokenRevokedError(AppError):
    """Raised for a syntactically valid, unexpired bearer token that was
    explicitly revoked (M5-E3-T1) — `POST /auth/logout` was called for it
    since it was issued. Its own distinct code (`token_revoked`), not
    folded into `InvalidTokenError`, since "this token was fine, then
    the user logged out" is a meaningfully different situation from
    "this token was never valid" for a caller/log reader to know."""

    def __init__(self) -> None:
        super().__init__(
            "This token has been revoked",
            code="token_revoked",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class RevocationCheckUnavailableError(AppError):
    """Raised when a token's revocation status genuinely cannot be
    determined — Redis is unreachable *and* the in-process write-through
    fallback (`RedisTokenBlocklist`'s own local copy of every revocation
    this process has issued) has no record for it either.

    Deliberately fails **closed**, not open: silently treating an
    unverifiable token as "not revoked" would mean a real logout, during
    a Redis outage, is quietly undone — defeating this feature's entire
    purpose. A `503`, not a `401`: this is a service degradation, not a
    claim that the caller's credentials are invalid.

    **Wider than it might look — read this before assuming the blast
    radius is small.** The write-through fallback only ever short-
    circuits *positively*: if it already has a record for this `jti`,
    `is_revoked` returns `True` without touching Redis at all. It gives
    no such shortcut the other way — "the fallback has no record" is
    never treated as proof the token wasn't revoked (a restart, or in a
    future multi-instance deployment, another process, could have
    revoked it without this process ever finding out), so a *fresh,
    never-revoked* token still requires a real Redis round trip to
    confirm. That means this error fires for **every** authenticated
    request during a Redis outage except ones using a token this exact
    process instance has itself already revoked — not a narrow edge
    case, but effectively the whole authenticated API, for as long as a
    configured Redis stays unreachable. Confirmed directly (not assumed):
    with a real, closed-port Redis connection substituted for a healthy
    one, a token revoked moments earlier via the same instance still
    correctly read `is_revoked() == True`; an entirely fresh, never-
    revoked token raised this error rather than returning `False`. This
    is the accepted, deliberate cost of failing closed rather than open
    for a security-relevant check with no way to verify itself — Redis
    becomes a hard dependency for authenticated traffic *only once an
    operator has explicitly opted into Redis-backed revocation* by
    setting `REDIS_URL`, not before.
    """

    def __init__(self) -> None:
        super().__init__(
            "Unable to verify this token's revocation status right now",
            code="revocation_check_unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class TokenExpiredError(AppError):
    """Raised for a syntactically valid bearer token past its own expiry."""

    def __init__(self) -> None:
        super().__init__(
            "Authentication token has expired",
            code="token_expired",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AuthNotConfiguredError(AppError):
    """Raised when a JWT operation is attempted with no `JWT_SECRET_KEY` set.

    A 500, not a 401 — this is a deployment misconfiguration, not
    anything the caller did wrong.
    """

    def __init__(self) -> None:
        super().__init__(
            "Authentication is not configured on this server (JWT_SECRET_KEY is unset)",
            code="auth_not_configured",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class EmailAlreadyRegisteredError(AppError):
    """Raised when creating a user whose email is already taken."""

    def __init__(self, email: str) -> None:
        super().__init__(
            f"A user with email {email!r} already exists",
            code="email_already_registered",
            status_code=status.HTTP_409_CONFLICT,
        )


class LoginLockedError(AppError):
    """Raised when `POST /auth/login` is locked out for the submitted
    email or the caller's IP (M5-E2-T1) — a dedicated brute-force /
    credential-stuffing defense, distinct from `InvalidCredentialsError`.

    The same generic message regardless of which key (email or IP)
    triggered it, and regardless of whether the submitted email belongs
    to a real user — `app.auth.login_lockout.LoginLockoutTracker` tracks
    the raw submitted email, never a resolved user id, so an unknown
    email locks out identically to a real one. `retry_after_seconds` is
    still surfaced (in the body and the `Retry-After` header) since
    *how long* to wait back off is not the same kind of information leak
    as *whether this account exists*.
    """

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            "Too many login attempts. Try again later.",
            code="too_many_login_attempts",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after_seconds)},
        )
