"""Experiment model — the AI Research & Training context's registry entry.

An `Experiment` records the configuration and outcome of one attempt at
building a model over a versioned ML dataset: which dataset build it used,
which features and targets, how the data was split, a placeholder model
type (no training engine exists yet — see `AI.md` § "Experiment Management"),
its lifecycle status, free-form notes, and a set of tags. `ExperimentMetric`
and `ExperimentArtifact` are child entities (evaluation numbers and
pointers to files/reports respectively) so an experiment's quantitative
results and its produced artifacts are each their own row, not a single
growing JSON blob.

`dataset_version`/`feature_set`/`target_config`/`split_config` are stored
as opaque strings/JSON rather than foreign keys: the ML Dataset Builder
(`app/ml_datasets/`) never persists a dataset to a database table — a
dataset is a computed-on-demand, exported artifact identified only by an
opaque `ml_dataset_id` (see `ARCHITECTURE.md` § "ML Dataset Builder"). An
experiment therefore references that identity as a copied string, the same
way a person would cite it in a lab notebook, not as a queryable relation
to a row that does not exist.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel, TimestampMixin

EXPERIMENT_STATUSES = ("draft", "running", "completed", "failed", "archived")

#: Every experiment starts here — a configuration recorded before any
#: outcome is known, mirroring how a researcher would register an attempt
#: before running it.
DEFAULT_EXPERIMENT_STATUS = "draft"


class Experiment(BaseModel, TimestampMixin):
    """One recorded attempt at building a model over a versioned ML dataset."""

    __tablename__ = "experiments"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    dataset_version: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="The ml_dataset_id (or dataset_id) this experiment was built over.",
    )
    feature_set: Mapped[list[dict] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Resolved feature requests used, e.g. [{'feature': 'sma', 'params': {...}}].",
    )
    target_config: Mapped[list[dict] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Resolved target requests used, e.g. [{'target': 'next_close', 'params': {...}}].",
    )
    split_config: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Split ratios used, e.g. {'train': 0.7, 'validation': 0.15, 'test': 0.15}.",
    )
    model_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Placeholder label only — no training engine exists yet.",
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default=DEFAULT_EXPERIMENT_STATUS,
        server_default=DEFAULT_EXPERIMENT_STATUS,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    tags: Mapped[list["ExperimentTag"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentTag.tag",
    )
    metrics: Mapped[list["ExperimentMetric"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentMetric.recorded_at",
    )
    artifacts: Mapped[list["ExperimentArtifact"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="ExperimentArtifact.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'running', 'completed', 'failed', 'archived')",
            name="status_valid",
        ),
    )


class ExperimentTag(BaseModel):
    """One tag on one experiment.

    Normalized as its own table rather than a JSON array, so a tag is a
    real, indexable, joinable column — matching this schema's existing
    preference for relational tables over blobs (see `Exchange`/`Market`/
    `Candle`, none of which use a JSON column anywhere).
    """

    __tablename__ = "experiment_tags"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)

    experiment: Mapped["Experiment"] = relationship(back_populates="tags")

    __table_args__ = (
        UniqueConstraint("experiment_id", "tag", name="uq_experiment_tags_experiment_tag"),
    )


class ExperimentMetric(BaseModel):
    """One evaluation metric recorded against an experiment (e.g. accuracy, sharpe_ratio)."""

    __tablename__ = "experiment_metrics"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    experiment: Mapped["Experiment"] = relationship(back_populates="metrics")

    __table_args__ = (Index("ix_experiment_metrics_experiment_name", "experiment_id", "name"),)


ARTIFACT_TYPES = ("dataset_export", "model_checkpoint", "report", "plot", "other")


class ExperimentArtifact(BaseModel, TimestampMixin):
    """A reference to an artifact produced by an experiment — a pointer, not stored file content.

    No object storage is wired into this platform yet (see `ARCHITECTURE.md`
    § "Known Limitations"), so `uri` is whatever locates the artifact today
    — a file path, an export filename, or a URL — and this table exists to
    make that reference itself queryable and reproducible, not to hold the
    artifact's bytes.
    """

    __tablename__ = "experiment_artifacts"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    experiment: Mapped["Experiment"] = relationship(back_populates="artifacts")

    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('dataset_export', 'model_checkpoint', 'report', 'plot', 'other')",
            name="artifact_type_valid",
        ),
    )
