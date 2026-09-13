"""Audit trail storage access."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLogEntry


class AuditLogRepository:
    """Create/read access to `audit_log`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: str | None,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=old_value,
            new_value=new_value,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def list_entries(
        self,
        *,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLogEntry], int]:
        """A page of audit entries, newest first, optionally filtered."""
        filters = []
        if user_id is not None:
            filters.append(AuditLogEntry.user_id == user_id)
        if resource_type is not None:
            filters.append(AuditLogEntry.resource_type == resource_type)
        if resource_id is not None:
            filters.append(AuditLogEntry.resource_id == resource_id)

        count_stmt = select(func.count()).select_from(AuditLogEntry)
        for condition in filters:
            count_stmt = count_stmt.where(condition)
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = select(AuditLogEntry)
        for condition in filters:
            stmt = stmt.where(condition)
        stmt = stmt.order_by(AuditLogEntry.created_at.desc()).limit(limit).offset(offset)
        entries = list((await self.session.execute(stmt)).scalars().all())
        return entries, total
