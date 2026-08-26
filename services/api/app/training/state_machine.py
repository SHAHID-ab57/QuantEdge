"""The training job lifecycle state machine.

A `TrainingJob.status` may only move along the edges below — enforced here
in application code (mirroring how `Experiment.status` is enforced by a
database `CHECK` constraint for its *value set*; this adds the *transition*
rule a `CHECK` constraint cannot express on its own):

    pending -> running -> completed
                        -> failed
    pending -> cancelled
    running -> cancelled

`completed`, `failed`, and `cancelled` are terminal — no further transition
is ever allowed out of them, matching `archived` being the closest
`Experiment` analogue of "done, not going back."
"""

from app.training.errors import (
    InvalidTrainingJobTransitionError,  # noqa: F401  (re-export for callers)
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


def can_transition(current: str, target: str) -> bool:
    """Whether moving from `current` to `target` is a legal lifecycle transition."""
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_transition_allowed(current: str, target: str) -> None:
    """Raise `InvalidTrainingJobTransitionError` unless `current -> target` is legal."""
    if not can_transition(current, target):
        raise InvalidTrainingJobTransitionError(current, target)
