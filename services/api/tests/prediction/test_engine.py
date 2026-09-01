"""Unit tests for `app.prediction.engine` — pure, no database.

Proves the one thing `PredictionEngine.assemble` is responsible for: never
presenting a bare number as fact. A classifier's confidence/probabilities
are surfaced with a resolved horizon; a regressor's (or any adapter without
`predict_proba`) confidence is explicitly `None` with a human-readable
reason, never a fabricated value.
"""

from datetime import UTC, datetime

from app.prediction.engine import NO_CONFIDENCE_REASON, PredictionEngine, resolve_horizon
from app.schemas.experiments import TargetRequestDTO
from app.schemas.training import TrainingJobPredictResponse

AS_OF = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def target_config(*entries: tuple[str, str]) -> list[TargetRequestDTO]:
    return [
        TargetRequestDTO(target=target, params={"horizon": horizon}) for target, horizon in entries
    ]


class TestResolveHorizon:
    def test_matches_the_configured_targets_own_horizon(self) -> None:
        config = target_config(("next_direction", "3"))
        assert resolve_horizon(config, "next_direction_3") == 3

    def test_matches_by_prefix_when_several_targets_are_configured(self) -> None:
        config = target_config(("next_close", "1"), ("next_direction", "5"))
        assert resolve_horizon(config, "next_direction_5") == 5
        assert resolve_horizon(config, "next_close_1") == 1

    def test_returns_none_when_no_entry_matches(self) -> None:
        config = target_config(("next_close", "1"))
        assert resolve_horizon(config, "next_direction_5") is None

    def test_returns_none_for_an_empty_or_missing_target_config(self) -> None:
        assert resolve_horizon([], "next_direction_1") is None
        assert resolve_horizon(None, "next_direction_1") is None

    def test_returns_none_when_the_configured_horizon_is_not_a_real_number(self) -> None:
        config = [TargetRequestDTO(target="next_direction", params={"horizon": "not-a-number"})]
        assert resolve_horizon(config, "next_direction_1") is None

    def test_returns_none_when_the_matched_entry_has_no_horizon_param_at_all(self) -> None:
        config = [TargetRequestDTO(target="next_direction", params={})]
        assert resolve_horizon(config, "next_direction_1") is None


class TestAssemble:
    def test_a_classifiers_probabilities_produce_a_real_confidence_and_probability_map(
        self,
    ) -> None:
        engine = PredictionEngine()
        response = TrainingJobPredictResponse(
            predictions=["up"],
            feature_columns=["close", "sma_20"],
            classes=["down", "up"],
            probabilities=[[0.2, 0.8]],
            confidence_levels=["high"],
        )

        outcome = engine.assemble(
            target_column="next_direction_1",
            target_config=target_config(("next_direction", "1")),
            as_of=AS_OF,
            predict_response=response,
        )

        assert outcome.predicted_value == "up"
        assert outcome.horizon == 1
        assert outcome.as_of == AS_OF
        assert outcome.confidence == 0.8
        assert outcome.confidence_unavailable_reason is None
        assert outcome.probabilities == {"down": 0.2, "up": 0.8}
        assert outcome.classes == ["down", "up"]

    def test_a_regressor_has_no_confidence_and_an_explained_reason(self) -> None:
        engine = PredictionEngine()
        response = TrainingJobPredictResponse(
            predictions=[123.45],
            feature_columns=["close", "sma_20"],
            classes=None,
            probabilities=None,
            confidence_levels=None,
        )

        outcome = engine.assemble(
            target_column="next_close_1",
            target_config=target_config(("next_close", "1")),
            as_of=AS_OF,
            predict_response=response,
        )

        assert outcome.predicted_value == 123.45
        assert outcome.confidence is None
        assert outcome.confidence_unavailable_reason == NO_CONFIDENCE_REASON
        assert outcome.probabilities is None
        assert outcome.classes is None

    def test_confidence_is_the_predicted_classes_own_probability_not_just_the_max(self) -> None:
        """Adversarial: three classes, the predicted label is *not* the argmax of
        `probabilities` in insertion order — proves `confidence` is `max(row)`
        (the predicted class's own probability, since the model always predicts
        its own argmax) rather than, say, the first or last entry."""
        engine = PredictionEngine()
        response = TrainingJobPredictResponse(
            predictions=["flat"],
            feature_columns=["close"],
            classes=["down", "flat", "up"],
            probabilities=[[0.1, 0.75, 0.15]],
            confidence_levels=["high"],
        )

        outcome = engine.assemble(
            target_column="next_direction_1",
            target_config=target_config(("next_direction", "1")),
            as_of=AS_OF,
            predict_response=response,
        )

        assert outcome.confidence == 0.75
        assert outcome.probabilities == {"down": 0.1, "flat": 0.75, "up": 0.15}
