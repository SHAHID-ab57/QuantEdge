"""Tests for `compare` — picking a winner per metric across candidates."""

from datetime import UTC, datetime

from app.evaluation.base import Metric, MetricMetadata
from app.evaluation.benchmark import BenchmarkCandidate, compare
from app.evaluation.registry import MetricRegistry


class _LowerIsBetterMetric(Metric):
    metadata = MetricMetadata(
        name="loss",
        label="Loss",
        description="test double, lower is better",
        category="regression",
        higher_is_better=False,
    )

    def compute(self, y_true, y_pred, y_proba=None):  # noqa: ANN001, ANN201 - test double
        return 0.0


def _candidate(job_id: str, **metrics: float) -> BenchmarkCandidate:
    return BenchmarkCandidate(
        training_job_id=job_id,
        experiment_id="exp-1",
        experiment_name="Experiment One",
        model_type=f"model-{job_id}",
        model_kind="classification",
        dataset_version="ds-1",
        target_column="next_direction",
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
        metrics=metrics,
    )


class TestCompare:
    def test_picks_the_max_for_an_unregistered_metric_by_default(self) -> None:
        candidates = [_candidate("a", accuracy=0.7), _candidate("b", accuracy=0.9)]
        result = compare(candidates, MetricRegistry())
        entry = next(e for e in result.best_by_metric if e.metric == "accuracy")
        assert entry.training_job_id == "b"
        assert entry.higher_is_better is True

    def test_picks_the_min_for_a_registered_lower_is_better_metric(self) -> None:
        registry = MetricRegistry()
        registry.register(_LowerIsBetterMetric)
        candidates = [_candidate("a", loss=0.5), _candidate("b", loss=0.1)]

        result = compare(candidates, registry)

        entry = next(e for e in result.best_by_metric if e.metric == "loss")
        assert entry.training_job_id == "b"
        assert entry.higher_is_better is False

    def test_a_metric_present_on_only_some_candidates_still_gets_a_winner(self) -> None:
        candidates = [_candidate("a", accuracy=0.7, f1=0.6), _candidate("b", accuracy=0.9)]
        result = compare(candidates, MetricRegistry())
        metric_names = {e.metric for e in result.best_by_metric}
        assert metric_names == {"accuracy", "f1"}
        f1_entry = next(e for e in result.best_by_metric if e.metric == "f1")
        assert f1_entry.training_job_id == "a"

    def test_every_candidate_is_returned_unchanged(self) -> None:
        candidates = [_candidate("a", accuracy=0.7), _candidate("b", accuracy=0.9)]
        result = compare(candidates, MetricRegistry())
        assert result.candidates == candidates

    def test_empty_candidates_yields_an_empty_result(self) -> None:
        result = compare([], MetricRegistry())
        assert result.candidates == []
        assert result.best_by_metric == []
