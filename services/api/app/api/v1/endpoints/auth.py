"""Authentication + audit trail API (M5-E1-T1).

`POST /auth/login` is the one unauthenticated endpoint here — everything
else on this platform that mutates state now requires the bearer token
it issues (`app.dependencies.auth.get_current_user`). `GET /audit-log`
is read-only but still requires authentication: an audit trail naming
who did what is itself sensitive.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies.auth import get_audit_service, get_auth_service, get_current_user
from app.models.user import User
from app.schemas.audit import AuditLogEntryDTO, AuditLogListResponse
from app.schemas.auth import LoginRequest, TokenResponse, UserDTO
from app.services.audit import AuditService
from app.services.auth import AuthService

router = APIRouter(tags=["auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
AuditServiceDep = Annotated[AuditService, Depends(get_audit_service)]
CurrentUser = Annotated[User, Depends(get_current_user)]

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
        "registered accounts."
    ),
)
async def login(body: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    """Verify credentials and issue a bearer token."""
    return await service.login(email=body.email, password=body.password)


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
