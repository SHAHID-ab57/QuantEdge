"""The audit trail — real, queryable rows with a genuine user identity.

Upgrades, rather than duplicates, the log-line-based account-configuration
traceability `feat(paper-trading): log account-configuration changes for
traceability` (commit `6104fcd`) added: that work explicitly deferred "a
real audit table... and authentication" as Milestone 5's own project,
because there was no user identity to attach to anything at the time.
This is that table. The `logger.info` lines it upgrades stay in place —
this is additive, not a removal of the existing, human-readable log
trail — but every one of them now has a corresponding, permanently
queryable row naming exactly which authenticated user did it.
"""

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin

__all__ = ["AuditLogEntry"]


class AuditLogEntry(BaseModel, TimestampMixin):
    """One attributed, timestamped mutation performed through the API.

    `resource_id` is stored as a plain string, not a `Uuid` column —
    resource ids across this platform's own domains are a mix of `UUID`
    (accounts, experiments, training jobs) and other shapes (a market
    symbol, a dataset build id); a single, honest text column that never
    needs a type per action beats a nullable column per possible id type.
    `old_value`/`new_value` are free-form JSON, one row's own snapshot of
    "what changed" — `None` for an action with no natural one side (a
    `create` has no meaningful `old_value`; a `delete` has no meaningful
    `new_value`).
    """

    __tablename__ = "audit_log"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="The authenticated user who performed this action — every row has one; "
        "this table is only ever written from an authenticated request path.",
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="A short, stable action name, e.g. 'paper_account.create', "
        "'paper_trading.strategy_enabled'.",
    )
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="What kind of thing changed, e.g. 'paper_account', 'training_job'.",
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="The specific resource's id, as text — None for an action with no "
        "single identifiable resource.",
    )
    old_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="A snapshot of the relevant fields before this action, or None when "
        "the action has no natural 'before' (e.g. a create).",
    )
    new_value: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="A snapshot of the relevant fields after this action, or None when "
        "the action has no natural 'after' (e.g. a delete).",
    )
