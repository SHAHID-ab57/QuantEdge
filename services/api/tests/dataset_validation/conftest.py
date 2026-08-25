"""Shared dataset-construction helpers for the validation engine's tests.

Every rule is tested against a hand-built ``FeatureDataset`` rather than a
real pipeline run, mirroring the registry/pipeline tests' "isolated,
throwaway" convention (see ``tests/features/test_registry.py``): a rule's
job is to check a dataset's *shape*, and a hand-built one can express
exactly the shape being tested (a duplicate timestamp, a NaN cell, a
mismatched dtype) without needing a real generator that happens to produce
it.
"""

from datetime import UTC, datetime, timedelta

from app.features.base import FeatureColumn, FeatureValue
from app.features.dataset import DatasetFeatureInfo, FeatureDataset
from app.features.quality import DatasetQualityReport, FeatureFailure

__all__ = ["make_dataset"]


def make_dataset(
    *,
    columns: list[FeatureColumn] | None = None,
    rows: list[list[FeatureValue]] | None = None,
    timestamps: list[datetime] | None = None,
    features: list[DatasetFeatureInfo] | None = None,
    failures: list[FeatureFailure] | None = None,
    symbol: str = "ETHUSD",
    timeframe: str = "1h",
    dataset_id: str = "test-dataset",
    null_counts: dict[str, int] | None = None,
    rows_returned: int | None = None,
) -> FeatureDataset:
    """Build a ``FeatureDataset`` directly, without running the pipeline."""
    if columns is None:
        columns = [FeatureColumn(name="close", label="Close", dtype="float")]
    if timestamps is None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        timestamps = [base + timedelta(hours=i) for i in range(3)]
    if rows is None:
        rows = [[100.0 + i] for i in range(len(timestamps))]
    if features is None:
        features = [
            DatasetFeatureInfo(
                feature="ohlcv",
                label="OHLCV",
                version="1.0.0",
                params={},
                columns=[column.name for column in columns],
                warmup=0,
                execution_time_ms=0.1,
            )
        ]
    quality = DatasetQualityReport(
        total_rows=len(rows),
        rows_returned=rows_returned if rows_returned is not None else len(rows),
        rows_removed=0,
        null_counts=null_counts or {},
        feature_failures=failures or [],
    )
    return FeatureDataset(
        dataset_id=dataset_id,
        symbol=symbol,
        timeframe=timeframe,
        columns=columns,
        timestamps=timestamps,
        rows=rows,
        features=features,
        candles_analyzed=len(rows),
        rows_dropped=0,
        warmup_candles=0,
        pipeline_version="1.0.0",
        generated_at=datetime.now(UTC),
        quality=quality,
    )
