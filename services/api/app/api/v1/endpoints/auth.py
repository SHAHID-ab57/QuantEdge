"""Authentication + audit trail API (M5-E1-T1; token revocation, M5-E3-T1).

`POST /auth/login` is the one unauthenticated endpoint here — everything
else on this platform that mutates state now requires the bearer token
it issues (`app.dependencies.auth.get_current_user`). `GET /audit-log`
is read-only but still requires authentication: an audit trail naming
who did what is itself sensitive.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.auth.errors import InvalidCredentialsError, LoginLockedError
from app.auth.login_lockout import LoginLockout
from app.auth.security import TokenClaims
from app.auth.token_revocation import TokenBlocklist
from app.dependencies.auth import (
    get_audit_service,
    get_auth_service,
    get_client_ip,
    get_current_token_claims,
    get_current_user,
    get_login_lockout_tracker,
    get_token_blocklist,
)
from app.models.user import User
from app.schemas.audit import AuditLogEntryDTO, AuditLogListResponse
from app.schemas.auth import LoginRequest, TokenResponse, UserDTO
from app.services.audit import AuditService
from app.services.auth import AuthService, normalize_email

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentTokenClaims = Annotated[TokenClaims, Depends(get_current_token_claims)]
LoginLockoutDep = Annotated[LoginLockout, Depends(get_login_lockout_tracker)]
TokenBlocklistDep = Annotated[TokenBlocklist, Depends(get_token_blocklist)]
ClientIp = Annotated[str, Depends(get_client_ip)]

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Log in with email and password",
    description=(
        "Verify credentials and issue a bearer JWT. There is no self-registration "
        "endpoint — a user account is created with `make create-user` on the "
        "server, matching this platform's own small-real-users scope. The same "
        "`invalid_credentials` error (401) is returned for an unknown email and a "
        "wrong password, so a login attempt can never be used to enumerate "
        "registered accounts. Locked out (429, `too_many_login_attempts`) after "
        "repeated failures for the same email or the same client IP — see "
        "`ARCHITECTURE.md` § 'Authentication & Audit Trail' → 'Login lockout'."
    ),
)
async def login(
    body: LoginRequest,
    service: AuthServiceDep,
    lockout: LoginLockoutDep,
    client_ip: ClientIp,
) -> TokenResponse:
    """Verify credentials and issue a bearer token, enforcing the login
    lockout (M5-E2-T1, Redis-backed since M5-E3-T1) before and after the
    credential check.

    Keyed by the *submitted* email (normalized, never resolved to a real
    user id) and separately by `client_ip` — either key alone can lock
    this out, so an unknown email locks out identically to a real one,
    preserving `InvalidCredentialsError`'s own enumeration-resistance.
    """
    email_key = f"email:{normalize_email(body.email)}"
    ip_key = f"ip:{client_ip}"

    locked_for = max(await lockout.seconds_locked(email_key), await lockout.seconds_locked(ip_key))
    if locked_for > 0:
        logger.warning(
            "Login rejected: already locked out (email=%s ip=%s retry_after=%.0fs)",
            normalize_email(body.email),
            client_ip,
            locked_for,
        )
        raise LoginLockedError(retry_after_seconds=int(locked_for) + 1)

    try:
        token = await service.login(email=body.email, password=body.password)
    except InvalidCredentialsError:
        email_just_locked = await lockout.record_failure(email_key)
        ip_just_locked = await lockout.record_failure(ip_key)
        if email_just_locked or ip_just_locked:
            logger.warning(
                "Login locked out after repeated failures (email=%s ip=%s "
                "locked_by_email=%s locked_by_ip=%s)",
                normalize_email(body.email),
                client_ip,
                email_just_locked,
                ip_just_locked,
            )
        raise

    await lockout.record_success(email_key)
    await lockout.record_success(ip_key)
    return token


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out — revokes the calling token server-side",
    description=(
        "Blocklists the calling token's own `jti` for the remainder of its natural "
        "lifetime (M5-E3-T1), so it can no longer authenticate anything even if it was "
        "already captured — closing the gap M5-E1-T1 disclosed, where logout only ever "
        "cleared the token client-side and a captured token stayed fully valid and "
        "replayable until natural expiry. Only revokes *this* token, naming this one "
        "session — a user's other, still-valid tokens from other sessions are "
        "unaffected. Idempotent: logging out an already-logged-out token is a no-op, "
        "not an error."
    ),
)
async def logout(claims: CurrentTokenClaims, blocklist: TokenBlocklistDep) -> None:
    """Revoke the calling token so it can no longer authenticate anything."""
    ttl_seconds = (claims.expires_at - datetime.now(UTC)).total_seconds()
    await blocklist.revoke(claims.jti, ttl_seconds=ttl_seconds)


@router.get(
    "/auth/me",
    response_model=UserDTO,
    summary="The current authenticated user",
    description="Return the caller's own profile — the frontend's own session check.",
)
async def get_me(current_user: CurrentUser) -> UserDTO:
    """Return the authenticated caller's own profile."""
    return UserDTO(id=current_user.id, email=current_user.email, created_at=current_user.created_at)


@router.get(
    "/audit-log",
    response_model=AuditLogListResponse,
    summary="List audit trail entries",
    description=(
        "A page of recorded mutations, newest first — who did what, when. "
        "Requires authentication (any logged-in user may read the full trail; "
        "this platform draws no admin/member distinction, see `ARCHITECTURE.md` "
        '§ "Authentication & Audit Trail"). Optional filters: `user_id`, '
        "`resource_type`, `resource_id`."
    ),
)
async def list_audit_log(
    _current_user: CurrentUser,
    service: AuditServiceDep,
    user_id: Annotated[uuid.UUID | None, Query(description="Filter to one user")] = None,
    resource_type: Annotated[
        str | None, Query(description="Filter to one resource type, e.g. 'paper_account'")
    ] = None,
    resource_id: Annotated[str | None, Query(description="Filter to one resource id")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    """Return a page of audit trail entries, newest first."""
    entries, total = await service.list_entries(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(
        entries=[AuditLogEntryDTO.model_validate(entry) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )
