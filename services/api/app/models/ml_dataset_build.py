"""MLDatasetBuild — a persisted record of one ML Dataset Builder run.

The ML Dataset Builder itself (`app/ml_datasets/`) still builds a dataset
entirely in memory and returns nothing durable on its own — that design
choice (`ARCHITECTURE.md` § "ML Dataset Builder") is unchanged. This table
is the layer *above* it: `MLDatasetService.build_dataset` (the method
`POST /markets/{symbol}/ml/dataset` calls) now also persists the exact
response it returns, so a researcher can come back later and reopen a past
build — see the "Dataset History" surface in `AI.md`.

Deliberately stores the **entire** built dataset (every row, verbatim, in
`payload`) rather than only its configuration/summary: unlike `Experiment`'s
`dataset_version` (an intentionally abstract citation) or `TrainingJob`'s
similar citation, this table's whole purpose is "let me see this exact
dataset again," which a citation alone cannot do without re-touching
candles. This is safe at this platform's current scale because every build
is already row-capped by `Settings.candles_max_limit` (1000 rows) — a
`payload` JSON blob stays small even at that cap. If dataset sizes ever grow
far beyond that, this table is the one place to revisit (e.g. moving
`payload` to object storage and keeping only a URI here), not a redesign of
the builder itself.
"""

from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel, TimestampMixin


class MLDatasetBuild(BaseModel, TimestampMixin):
    """One persisted `POST /markets/{symbol}/ml/dataset` response, verbatim."""

    __tablename__ = "ml_dataset_builds"

    ml_dataset_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="The engine's own per-build id (MLDataset.ml_dataset_id), duplicated for lookup.",
    )
    symbol: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    row_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Denormalized from payload, for a cheap list view."
    )
    column_count: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_passed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, comment="The Dataset Validation Engine's verdict for this build."
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        comment="The full, untruncated MLDatasetResponse this build produced (rows included).",
    )
