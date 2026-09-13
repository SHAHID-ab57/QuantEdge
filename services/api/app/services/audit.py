"""The audit trail's own write path — one place every mutating endpoint
(or the service behind it) records who did what.

Two depths of detail exist on this platform, both writing into the same
`audit_log` table:

- **Rich** — `app.services.paper_trading.PaperTradingService` calls this
  directly from inside each mutating method, where the actual old/new
  domain values are already local variables (the same values its own
  `logger.info` lines already report) — this is the account-configuration
  traceability gap the motivating incident actually exposed, so it gets
  full before/after detail.
- **Generic** — every other mutating endpoint (experiments, training
  jobs, backtests, predictions, evaluation benchmarks/history) records
  `action`/`resource_type`/`resource_id` with `old_value`/`new_value` left
  `None`, called from the router layer right after the underlying service
  call succeeds. These endpoints' own services don't already carry
  before/after state the way `PaperTradingService`'s partial-update
  methods do (a `create` has no "before"; a `delete` has no "after"), so
  richer detail would mean re-deriving it, not reusing it — a scope this
  task's own "don't over-build" instruction argues against. Every
  mutating action is still attributed to a real user; only the paper
  trading domain gets the full before/after snapshot for now.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from app.models.audit_log import AuditLogEntry
from app.repositories.audit_log import AuditLogRepository


@dataclass
class AuditService:
    """Records and lists audit trail entries."""

    audit_log_repository: AuditLogRepository

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> AuditLogEntry:
        return await self.audit_log_repository.create(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            old_value=old_value,
            new_value=new_value,
        )

    async def list_entries(
        self,
        *,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[AuditLogEntry], int]:
        return await self.audit_log_repository.list_entries(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
            offset=offset,
        )
