"""Tests for the training job lifecycle state machine — pure, no database."""

import pytest

from app.training.errors import InvalidTrainingJobTransitionError
from app.training.state_machine import assert_transition_allowed, can_transition


class TestCanTransition:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("pending", "running"),
            ("pending", "cancelled"),
            ("running", "completed"),
            ("running", "failed"),
            ("running", "cancelled"),
        ],
    )
    def test_allows_every_legal_edge(self, current: str, target: str) -> None:
        assert can_transition(current, target) is True

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            ("pending", "completed"),
            ("pending", "failed"),
            ("completed", "running"),
            ("failed", "running"),
            ("cancelled", "running"),
            ("completed", "cancelled"),
            ("running", "pending"),
        ],
    )
    def test_rejects_every_illegal_edge(self, current: str, target: str) -> None:
        assert can_transition(current, target) is False

    @pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
    def test_terminal_statuses_have_no_outgoing_edges(self, terminal: str) -> None:
        for target in ("pending", "running", "completed", "failed", "cancelled"):
            assert can_transition(terminal, target) is False


class TestAssertTransitionAllowed:
    def test_does_not_raise_for_a_legal_transition(self) -> None:
        assert_transition_allowed("pending", "running")

    def test_raises_for_an_illegal_transition(self) -> None:
        with pytest.raises(InvalidTrainingJobTransitionError) as exc_info:
            assert_transition_allowed("completed", "running")
        assert exc_info.value.code == "invalid_training_job_transition"
        assert exc_info.value.status_code == 409
