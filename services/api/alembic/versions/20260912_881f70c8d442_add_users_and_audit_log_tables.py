"""add users and audit_log tables

Revision ID: 881f70c8d442
Revises: 252f1e39f532
Create Date: 2026-09-12 19:39:12.416069

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "881f70c8d442"
down_revision: str | None = "252f1e39f532"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also re-detected the same two pre-existing drifts every
    # migration since 35fe2827d1fb has found and skipped — a comment-only
    # wording drift on ml_dataset_builds.ml_dataset_id and a cosmetic
    # check-constraint name truncation on paper_strategy_decisions. Left out
    # again here; not this migration's concern (see 156feb63e12d's note).
    op.create_table(
        "users",
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=False,
            comment="Login identifier, stored lowercased by the application layer.",
        ),
        sa.Column(
            "hashed_password",
            sa.String(length=255),
            nullable=False,
            comment="A bcrypt hash — never plaintext, never a reversible encoding.",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "audit_log",
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
            comment="The authenticated user who performed this action — every row has "
            "one; this table is only ever written from an authenticated request path.",
        ),
        sa.Column(
            "action",
            sa.String(length=100),
            nullable=False,
            comment="A short, stable action name, e.g. 'paper_account.create', "
            "'paper_trading.strategy_enabled'.",
        ),
        sa.Column(
            "resource_type",
            sa.String(length=100),
            nullable=False,
            comment="What kind of thing changed, e.g. 'paper_account', 'training_job'.",
        ),
        sa.Column(
            "resource_id",
            sa.String(length=255),
            nullable=True,
            comment="The specific resource's id, as text — None for an action with no "
            "single identifiable resource.",
        ),
        sa.Column(
            "old_value",
            sa.JSON(),
            nullable=True,
            comment="A snapshot of the relevant fields before this action, or None when "
            "the action has no natural 'before' (e.g. a create).",
        ),
        sa.Column(
            "new_value",
            sa.JSON(),
            nullable=True,
            comment="A snapshot of the relevant fields after this action, or None when "
            "the action has no natural 'after' (e.g. a delete).",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_log_user_id_users"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(op.f("ix_audit_log_action"), "audit_log", ["action"], unique=False)
    op.create_index(op.f("ix_audit_log_resource_id"), "audit_log", ["resource_id"], unique=False)
    op.create_index(
        op.f("ix_audit_log_resource_type"), "audit_log", ["resource_type"], unique=False
    )
    op.create_index(op.f("ix_audit_log_user_id"), "audit_log", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_log_user_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_resource_type"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_resource_id"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_action"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
