"""Wire schemas (DTOs) for authentication."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, EmailStr, Field, field_serializer

#: Matches bcrypt's own hard 72-byte limit (`app/auth/security.py`) — capped
#: here so an over-length password is a normal 422 validation error, not a
#: raw bcrypt `ValueError` surfacing from inside the service layer.
_MAX_PASSWORD_LENGTH = 72


class LoginRequest(BaseModel):
    """Email + password login."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=_MAX_PASSWORD_LENGTH)


class TokenResponse(BaseModel):
    """A freshly issued bearer token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Seconds until this token expires")


class UserDTO(BaseModel):
    """The authenticated user's own public profile — no password hash, ever."""

    id: uuid.UUID
    email: str
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
