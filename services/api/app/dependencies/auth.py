"""Dependency providers for authentication and the audit trail.

`get_current_user` is the one dependency every protected mutating
endpoint declares — `Annotated[User, Depends(get_current_user)]` — the
same shape every other per-request dependency on this platform already
takes.
"""

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.errors import InvalidTokenError, MissingCredentialsError
from app.auth.login_lockout import LoginLockoutTracker
from app.auth.security import decode_access_token
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.user import User
from app.repositories.audit_log import AuditLogRepository
from app.repositories.users import UserRepository
from app.services.audit import AuditService
from app.services.auth import AuthService

#: `auto_error=False` so a missing header raises this module's own typed
#: `MissingCredentialsError` (a consistent `{code, detail}` body, matching
#: every other domain error on this platform) rather than FastAPI's
#: default bare 403.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    """Build the auth service wired to the request session."""
    return AuthService(user_repository=UserRepository(session), settings=settings)


def get_audit_service(session: Annotated[AsyncSession, Depends(get_db)]) -> AuditService:
    """Build the audit service wired to the request session."""
    return AuditService(audit_log_repository=AuditLogRepository(session))


def get_login_lockout_tracker(request: Request) -> LoginLockoutTracker:
    """The per-app `LoginLockoutTracker` created in `create_app`
    (`app.state.login_lockout_tracker`) — see that module's own
    docstring for why this lives on `app.state` rather than as a
    module-level singleton."""
    return request.app.state.login_lockout_tracker  # type: ignore[no-any-return]


def get_client_ip(request: Request) -> str:
    """The requesting client's IP address, or `"unknown"` when Starlette
    couldn't determine one (e.g. certain test transports) — used only as
    a rate-limit/lockout key, never for anything security-load-bearing
    on its own."""
    client = request.client
    return client.host if client is not None else "unknown"


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """Resolve the authenticated user from a bearer token, or raise a 401.

    Every mutating endpoint on this platform declares this dependency —
    a missing header, a malformed/expired token, or a token whose subject
    no longer resolves to a real user (a deleted account) all raise a
    real 401, never a silent pass-through.
    """
    if credentials is None:
        raise MissingCredentialsError()
    user_id = decode_access_token(credentials.credentials, settings=settings)
    user = await auth_service.get_user(user_id)
    if user is None:
        raise InvalidTokenError("Token does not correspond to a real user")
    return user
