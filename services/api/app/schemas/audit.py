"""Wire schemas (DTOs) for the audit trail API."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_serializer


class AuditLogEntryDTO(BaseModel):
    """One recorded, attributed mutation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    action: str
    resource_type: str
    resource_id: str | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class AuditLogListResponse(BaseModel):
    """A page of audit trail entries, newest first."""

    entries: list[AuditLogEntryDTO]
    total: int
    limit: int
    offset: int
