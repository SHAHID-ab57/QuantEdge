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
