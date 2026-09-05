"""add external data points

Revision ID: fadfaba274eb
Revises: 9a50eaff41a2
Create Date: 2026-09-05 21:13:19.465953

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fadfaba274eb"
down_revision: str | None = "9a50eaff41a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Autogenerate also detected two drifts unrelated to this migration's
    # own change, both left out again here:
    # 1. A one-word comment-only drift on ml_dataset_builds.ml_dataset_id
    #    ("duplicated for lookup" vs "duplicated here for lookup") — see
    #    the identical note in 35fe2827d1fb, 2f9216bd92c0, 7a3254fe72af,
    #    c1e00878df40, and 16e4c2531e7d, which each found and skipped it.
    # 2. A check-constraint *name* drift on paper_strategy_decisions: the
    #    real, already-applied name is Postgres's own >63-byte truncation
    #    (`..._act_c182`) of what SQLAlchemy's naming convention computes
    #    from the model unabridged (`..._action_valid`) — a cosmetic
    #    rename with no behavior change, introduced by 9a50eaff41a2 and
    #    not this migration's concern to fix.
    op.create_table(
        "external_data_points",
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            comment="The registered connector's own source identifier, e.g. 'fear_greed' "
            "(app.connectors.registry.ConnectorMetadata.source).",
        ),
        sa.Column(
            "symbol",
            sa.String(length=50),
            nullable=True,
            comment="Market this point applies to; NULL for a source-wide/global value — "
            "Fear & Greed has no per-symbol variant.",
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When this value was observed/reported by the source itself — never "
            "the ingestion time (see ingested_at).",
        ),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column(
            "raw_payload",
            sa.JSON(),
            nullable=True,
            comment="The connector's own raw record for this point, kept for audit — "
            "never re-parsed by anything downstream.",
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When this platform actually stored the row — distinct from "
            "timestamp, which is when the source itself reported the value.",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_data_points")),
        sa.UniqueConstraint(
            "source", "symbol", "timestamp", name="uq_external_data_points_source_symbol_timestamp"
        ),
    )
    op.create_index(
        op.f("ix_external_data_points_source"), "external_data_points", ["source"], unique=False
    )
    op.create_index(
        op.f("ix_external_data_points_symbol"), "external_data_points", ["symbol"], unique=False
    )
    op.create_index(
        op.f("ix_external_data_points_timestamp"),
        "external_data_points",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_external_data_points_timestamp"), table_name="external_data_points")
    op.drop_index(op.f("ix_external_data_points_symbol"), table_name="external_data_points")
    op.drop_index(op.f("ix_external_data_points_source"), table_name="external_data_points")
    op.drop_table("external_data_points")
